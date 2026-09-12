import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
export function Modal({ title, close, children, className = '' }: { title: string; close: () => void; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null)
  const reduced = useReducedMotion()
  useEffect(() => {
    const dialog = ref.current
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog?.showModal()
    return () => { dialog?.close(); previous?.focus() }
  }, [])
  return <dialog ref={ref} className={'modal ' + className} aria-labelledby="modal-title" onCancel={e => { e.preventDefault(); close() }} onClick={e => { if (e.target === e.currentTarget) close() }}>
    <motion.div initial={{ opacity: 0, y: reduced ? 0 : 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .22 }}>
      <div className="modal-heading"><div><span className="eyebrow">SATBURN / OBSERVATION DESK</span><h2 id="modal-title">{title}</h2></div><button className="icon-button" aria-label="Close dialog" onClick={close} autoFocus><X size={20}/></button></div>{children}
    </motion.div>
  </dialog>
}
