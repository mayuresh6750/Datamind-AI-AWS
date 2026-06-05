"use client"
import React from "react";

export default function IntentChips({intents}:{intents:string[]}){
  return (
    <div className="flex gap-2">{intents.map(i=> <span key={i} className="px-2 py-1 bg-gray-100 rounded">{i}</span>)}</div>
  )
}
