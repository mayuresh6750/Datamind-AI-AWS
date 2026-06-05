"use client"
import React from "react";
import type { ReactNode } from "react";

export default function AuditRow({left,right}:{left:ReactNode; right?:ReactNode}){
  return (
    <div className="flex justify-between py-2 border-b">{left}{right && <div>{right}</div>}</div>
  )
}
