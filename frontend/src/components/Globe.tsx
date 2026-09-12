import { Component, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import type { ThreeEvent } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useReducedMotion } from 'framer-motion'
import { Crosshair, Globe2, RotateCcw } from 'lucide-react'
import * as THREE from 'three'
import { feature } from 'topojson-client'
import type { Topology } from 'topojson-specification'
import type { FeatureCollection, Geometry, Position } from 'geojson'
import world from 'world-atlas/countries-110m.json'
import type { Hotspot, Metadata } from '../api/schema'
import { BAND, CATEGORY, coordinates, numberText, observationTime } from '../lib/presentation'
import { CategoryBadge } from './Badges'

const RADIUS = 2
function earthTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 2048; canvas.height = 1024
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas drawing is unavailable.')
  ctx.fillStyle = '#101f2a'; ctx.fillRect(0, 0, 2048, 1024)
  const topology = world as unknown as Topology
  const countries = feature(topology, topology.objects.countries) as FeatureCollection<Geometry>
  const ring = (points: Position[]) => {
    points.forEach(([lon, lat], i) => {
      const x = (lon + 180) / 360 * 2048, y = (90 - lat) / 180 * 1024
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    })
    ctx.closePath()
  }
  ctx.lineWidth = .65; ctx.strokeStyle = '#39515a'; ctx.fillStyle = '#263d43'
  for (const f of countries.features) {
    if (f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon') {
      const polygons = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates
      for (const polygon of polygons) {
        ctx.beginPath(); polygon.forEach(ring); ctx.fill('evenodd'); ctx.stroke()
      }
    }
  }
  ctx.strokeStyle = '#4f6d752b'; ctx.lineWidth = .7
  for (let x = 0; x <= 2048; x += 2048 / 24) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 1024); ctx.stroke() }
  for (let y = 0; y <= 1024; y += 1024 / 12) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(2048, y); ctx.stroke() }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}
function Planet() {
  const texture = useMemo(earthTexture, [])
  useEffect(() => () => texture.dispose(), [texture])
  return <group>
    <mesh><sphereGeometry args={[RADIUS, 128, 96]}/><meshStandardMaterial map={texture} roughness={.93} metalness={.12}/></mesh>
    <mesh><sphereGeometry args={[2.035, 96, 64]}/><shaderMaterial transparent depthWrite={false} side={THREE.BackSide} blending={THREE.AdditiveBlending}
      vertexShader="varying vec3 n; varying vec3 v; void main(){ vec4 p=modelViewMatrix*vec4(position,1.0); n=normalize(normalMatrix*normal); v=normalize(-p.xyz); gl_Position=projectionMatrix*p; }"
      fragmentShader="varying vec3 n; varying vec3 v; void main(){ float glow=pow(1.0-abs(dot(normalize(n),normalize(v))),3.0); gl_FragColor=vec4(0.16,0.40,0.46,glow*0.24); }"/></mesh>
  </group>
}
function RegionOutline({ bounds }: { bounds: Metadata['geographic_bounds'] }) {
  const geometry = useMemo(() => {
    const { min_latitude: s, max_latitude: n, min_longitude: w, max_longitude: e } = bounds
    const pts: THREE.Vector3[] = []
    const corners = [[s, w], [s, e], [n, e], [n, w], [s, w]]
    for (let edge = 0; edge < 4; edge++) for (let step = 0; step < 24; step++) {
      const t = step / 24
      pts.push(new THREE.Vector3(...coordinates(corners[edge][0] * (1-t) + corners[edge+1][0]*t, corners[edge][1]*(1-t)+corners[edge+1][1]*t, 2.007)))
    }
    pts.push(pts[0]); return new THREE.BufferGeometry().setFromPoints(pts)
  }, [bounds])
  useEffect(() => () => geometry.dispose(), [geometry])
  return <lineLoop geometry={geometry}><lineBasicMaterial color="#d1b17d" transparent opacity={.6}/></lineLoop>
}
function MarkerInstances({ rows, select, hover, selectedId }: { rows: Hotspot[]; select: (id: string) => void; hover: (h: Hotspot | null) => void; selectedId: string | null }) {
  const markers = useRef<THREE.InstancedMesh>(null)
  const rings = useRef<THREE.InstancedMesh>(null)
  const { camera, gl } = useThree()
  const scratch = useMemo(() => ({ dummy: new THREE.Object3D(), up: new THREE.Vector3(0,0,1), color: new THREE.Color() }), [])
  const positions = useMemo(() => rows.map(h => new THREE.Vector3(...coordinates(h.latitude, h.longitude, 2.009))), [rows])
  useLayoutEffect(() => {
    for (let i = 0; i < rows.length; i++) {
      markers.current?.setColorAt(i, scratch.color.set(CATEGORY[rows[i].predicted_class].color))
      rings.current?.setColorAt(i, scratch.color.set(BAND[rows[i].risk_band].color))
    }
    if (markers.current?.instanceColor) markers.current.instanceColor.needsUpdate = true
    if (rings.current?.instanceColor) rings.current.instanceColor.needsUpdate = true
    gl.domElement.dataset.renderedHotspots = String(rows.length)
  }, [rows, gl, scratch])
  useFrame(() => {
    if (!markers.current || !rings.current) return
    for (let i = 0; i < positions.length; i++) {
      const p = positions[i], row = rows[i]
      const size = Math.max(.0005, camera.position.distanceTo(p) * .003)
      scratch.dummy.position.copy(p)
      scratch.dummy.quaternion.setFromUnitVectors(scratch.up, p.clone().normalize())
      scratch.dummy.scale.setScalar(size * (row.hotspot_id === selectedId ? 1.45 : 1))
      scratch.dummy.updateMatrix(); markers.current.setMatrixAt(i, scratch.dummy.matrix)
      scratch.dummy.scale.multiplyScalar(BAND[row.risk_band].ring)
      scratch.dummy.updateMatrix(); rings.current.setMatrixAt(i, scratch.dummy.matrix)
    }
    markers.current.instanceMatrix.needsUpdate = true; rings.current.instanceMatrix.needsUpdate = true
    markers.current.computeBoundingSphere(); rings.current.computeBoundingSphere()
  })
  const hit = (event: ThreeEvent<PointerEvent | MouseEvent>, action: (h: Hotspot) => void) => {
    if (event.instanceId === undefined) return
    const row = rows[event.instanceId]
    if (positions[event.instanceId].dot(camera.position.clone().sub(positions[event.instanceId])) <= 0) return
    event.stopPropagation(); action(row)
  }
  if (!rows.length) return null
  return <group>
    <instancedMesh key={'markers-' + rows.length} ref={markers} args={[undefined, undefined, rows.length]} frustumCulled={false}
      onPointerMove={e => hit(e, hover)} onPointerOut={() => hover(null)} onClick={e => hit(e, h => select(h.hotspot_id))}>
      <circleGeometry args={[1, 12]}/><meshBasicMaterial toneMapped={false} side={THREE.DoubleSide}/>
    </instancedMesh>
    <instancedMesh key={'rings-' + rows.length} ref={rings} args={[undefined, undefined, rows.length]} frustumCulled={false} raycast={() => undefined}>
      <ringGeometry args={[1.28, 1.55, 16]}/><meshBasicMaterial transparent opacity={.42} depthWrite={false} toneMapped={false} side={THREE.DoubleSide}/>
    </instancedMesh>
  </group>
}
function CameraRig({ focus, center, view, reset, reduced }: { focus: Hotspot | null; center: [number, number]; view: 'world' | 'region'; reset: number; reduced: boolean }) {
  const { camera } = useThree()
  const goal = useRef<THREE.Vector3 | null>(null)
  const [lat, lon] = center
  useEffect(() => {
    goal.current = new THREE.Vector3(...coordinates(focus?.latitude ?? lat, focus?.longitude ?? lon, focus ? 2.16 : view === 'world' ? 5.8 : 2.30))
    if (reduced) { camera.position.copy(goal.current); camera.lookAt(0,0,0); goal.current = null }
  }, [focus, lat, lon, view, reset, reduced, camera])
  useFrame((_, delta) => {
    if (goal.current) {
      camera.position.lerp(goal.current, 1 - Math.exp(-delta * 4))
      camera.lookAt(0, 0, 0)
      if (camera.position.distanceTo(goal.current) < .0001) goal.current = null
    }
  })
  return <OrbitControls enablePan={false} enableDamping={!reduced} dampingFactor={.09} minDistance={2.04} maxDistance={8}
    rotateSpeed={.45} zoomSpeed={.55} onStart={() => { goal.current = null }}/>
}
class GlobeBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <div className="globe-fallback" role="alert">The 3D view is unavailable. Enable WebGL2 or use the observation index below; all API records remain accessible.</div> : this.props.children }
}
export default function Globe({ rows, meta, selected, select, resetSelection }: {
  rows: Hotspot[]; meta: Metadata; selected: Hotspot | null; select: (id: string) => void; resetSelection: () => void;
}) {
  const [hover, setHover] = useState<Hotspot | null>(null)
  const [view, setView] = useState<'world' | 'region'>('world')
  const [reset, setReset] = useState(0)
  const reduced = !!useReducedMotion()
  const b = meta.geographic_bounds
  const center: [number, number] = [(b.min_latitude+b.max_latitude)/2, (b.min_longitude+b.max_longitude)/2]
  const currentHover = hover && rows.some(h => h.hotspot_id === hover.hotspot_id) ? hover : null
  const changeView = (next: 'world' | 'region') => { resetSelection(); setView(next); setReset(n => n+1); setHover(null) }
  return <section className="globe-panel" aria-label="Interactive 3D observation globe">
    <div className="globe-heading"><div><span className="eyebrow">ORBITAL PERSPECTIVE</span><h2>Every signal has a context.</h2></div><span className="globe-count">{rows.length} observations</span></div>
    <div className="globe-canvas" style={{ cursor: currentHover ? 'pointer' : 'grab' }}>
      <GlobeBoundary><Canvas camera={{ position: coordinates(center[0], center[1], 5.8), fov: 42, near: .01, far: 100 }}
        dpr={[1, 1.75]} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        fallback={<div className="globe-fallback" role="alert">WebGL2 is unavailable. Use the observation index below to inspect the snapshot.</div>}
        onCreated={({ gl }) => { gl.domElement.setAttribute('aria-label', 'SatBurn 3D globe; use the observation index for keyboard selection'); gl.domElement.dataset.globeReady = 'true' }}>
        <ambientLight intensity={1.65}/><directionalLight position={[5, 6, -7]} intensity={2.5} color="#d6eceb"/>
        <directionalLight position={[-4, 1, 2]} intensity={.7} color="#2c5365"/>
        <Planet/><RegionOutline bounds={b}/><MarkerInstances rows={rows} select={id => { setHover(null); select(id) }} hover={setHover} selectedId={selected?.hotspot_id ?? null}/>
        <CameraRig focus={selected} center={center} view={view} reset={reset} reduced={reduced}/>
      </Canvas></GlobeBoundary>
    </div>
    <div className="globe-coordinates"><span>WGS84 / REFERENCE GLOBE</span><strong>{b.min_latitude}–{b.max_latitude}°N <i>/</i> {b.min_longitude}–{b.max_longitude}°E</strong></div>
    {currentHover && <div className="marker-tooltip" role="tooltip"><CategoryBadge category={currentHover.predicted_class}/><code>{currentHover.hotspot_id}</code><p>Review score {numberText(currentHover.risk_score, 2)} · {numberText(currentHover.frp)} MW</p><p>{currentHover.persistence_count_30d} distinct persistence days ? {observationTime(currentHover)}</p><small>Click to inspect evidence</small></div>}
    <div className="globe-tools"><button onClick={() => changeView('region')}><Crosshair size={15}/>Focus region</button><button onClick={() => changeView('world')} aria-label="Reset globe view"><RotateCcw size={15}/><span>Reset view</span></button></div>
    <div className="globe-legend">{Object.values(CATEGORY).map(c => <span key={c.code}><i style={{ background: c.color }}/>{c.label}</span>)}<small><Globe2 size={12}/>Drag to orbit · scroll to zoom · rings show review band</small></div>
  </section>
}
