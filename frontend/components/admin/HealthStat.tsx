"use client"
import React from "react";

export default function HealthStat({label,value}:{label:string;value:string|number}){
  return <div className="p-3 border rounded">{label}: {value}</div>
}
