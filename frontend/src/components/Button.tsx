import type { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary'
}

export default function Button({ variant = 'primary', className = '', children, ...props }: ButtonProps) {
  const base = 'px-5 py-2 rounded-full text-sm font-medium transition-colors disabled:opacity-50'
  const variants = {
    primary: 'bg-accent text-on-accent hover:bg-accent-hover',
    secondary: 'bg-muted text-ink hover:bg-muted-hover',
  }
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  )
}
