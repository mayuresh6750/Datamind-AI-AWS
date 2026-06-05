"use client"
import React from 'react'

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={(props.className ?? '') + ' w-full border rounded px-3 py-2'}
    />
  )
}
