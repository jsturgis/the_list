import type { Metadata } from 'next'
import Link from 'next/link'
import AlertsLink from '@/components/AlertsLink'
import React from 'react'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] })
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'The List — SF Bay Area Music',
  description: "Steve's weekly SF Bay Area music listing, enriched and made browsable.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-page text-ink">
        <header className="border-b border-line-subtle bg-surface">
          <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-2">
            <Link href="/" className="font-bold text-lg tracking-tight">
              The List
            </Link>
            <span className="text-ink-faint text-sm">
              SF Bay Area Music
            </span>
            <AlertsLink />
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  )
}
