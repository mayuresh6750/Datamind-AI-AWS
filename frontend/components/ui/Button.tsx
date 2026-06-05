"use client"
import React from 'react'

export function Button({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={"px-3 py-2 bg-brand-blue text-white rounded-md " + (props.className ?? '')}
    >
      {children}
    </button>
  )
}
