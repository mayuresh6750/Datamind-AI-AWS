import axios from "axios";

export async function refreshToken(refreshToken: string){
  const res = await axios.post('/api/auth/refresh',{refreshToken});
  return res.data;
}

export function setAuthHeader(token?:string){
  if(token) axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  else delete axios.defaults.headers.common["Authorization"];
}

function base64UrlDecode(input: string){
  // Replace URL-safe characters
  input = input.replace(/-/g, '+').replace(/_/g, '/');
  const pad = input.length % 4;
  if(pad) input += '='.repeat(4 - pad);
  // atob is available in browser and Edge runtime
  const decoded = atob(input);
  try{
    // Decode percent-encoded utf-8
    return decodeURIComponent(Array.prototype.map.call(decoded, (c: string) => {
      return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));
  }catch{
    return decoded;
  }
}

export async function verifyJwt(token: string | undefined | null){
  if(!token) return null;
  try{
    const parts = token.split('.');
    if(parts.length < 2) return null;
    const payload = JSON.parse(base64UrlDecode(parts[1]));
    return payload;
  }catch{
    return null;
  }
}
