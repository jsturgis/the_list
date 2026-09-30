import type { Metadata } from 'next'
import React from 'react'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] })
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'The List — SF Bay Area Music',
  description: "Steve's weekly SF Bay Area music listing, enriched and made browsable.",
}

export default function RootLayout({
  children,
  modal,
}: {
  children: React.ReactNode
  modal: React.ReactNode
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-50">
        <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
          <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-2">
            <a href="/" className="font-bold text-lg tracking-tight">
              The List
            </a>
            <span className="text-zinc-400 dark:text-zinc-500 text-sm">
              SF Bay Area Music
            </span>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-4 py-6">{children}</main>
        {modal}
      </body>
    </html>
  )
}
