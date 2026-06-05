"use client"
import React from 'react'

export function Label({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className='text-sm font-medium block mb-1'>
      {children}
    </label>
  )
}
