"use client"
import React from "react";

export default function UserRow({email,role}:{email:string;role:string}){
  return <div className="flex justify-between py-2 border-b"><div>{email}</div><div className="text-sm text-muted-foreground">{role}</div></div>
}
