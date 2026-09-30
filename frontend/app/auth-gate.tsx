"use client";
import {createContext, ReactNode, useContext, useEffect, useState} from "react";
import {api,jsonBody,setCsrfToken} from "../lib/api";
type Identity={id?:string;email:string;role:string};
type AuthResponse={user:Identity;csrf_token?:string;auth_enabled?:boolean};
const AuthContext=createContext<{user:Identity;logout:()=>void}>({user:{email:"",role:"VIEWER"},logout:()=>{}});
export const useAuth=()=>useContext(AuthContext);
export default function AuthGate({children}:{children:ReactNode}){
 const [user,setUser]=useState<Identity|null>(null),[pending,setPending]=useState(true),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 const accept=(response:AuthResponse)=>{setCsrfToken(response.csrf_token??"");setUser(response.user);};
 useEffect(()=>{const expired=()=>{setUser(null);setCsrfToken("");};window.addEventListener("boah-session-expired",expired);api<AuthResponse>("/auth/me").then(accept).catch(()=>{}).finally(()=>setPending(false));return()=>window.removeEventListener("boah-session-expired",expired);},[]);
 async function login(event:React.FormEvent<HTMLFormElement>){event.preventDefault();setError("");setBusy(true);const form=new FormData(event.currentTarget);try{accept(await api<AuthResponse>("/auth/login",{method:"POST",...jsonBody({email:form.get("email"),password:form.get("password")})}));}catch(e){setError(e instanceof Error?e.message:"Sign in failed");}finally{setBusy(false);}}
 async function logout(){try{await api("/auth/logout",{method:"POST"});setUser(null);setCsrfToken("");}catch(e){setError(e instanceof Error?e.message:"Sign out failed");}}
 if(pending)return <main className="login-screen"><p role="status">Connecting to your workspace…</p></main>;
 if(!user)return <main className="login-screen"><section className="login-card"><span className="brand-mark">B</span><p className="eyebrow">BUSINESS OPERATIONS AUTOMATION HUB</p><h1>Welcome back</h1><p className="muted">Sign in to your company workspace.</p><form onSubmit={login}><label>Email<input name="email" type="email" autoComplete="username" required autoFocus/></label><label>Password<input name="password" type="password" autoComplete="current-password" required/></label>{error&&<p className="error-banner" role="alert">{error}</p>}<button disabled={busy}>{busy?"Signing in…":"Sign in →"}</button></form><small className="muted">Your administrator manages access. Sessions stay in secure, HttpOnly cookies.</small></section></main>;
 return <AuthContext.Provider value={{user,logout}}>{error&&<div role="alert" className="error-banner">{error}</div>}{children}</AuthContext.Provider>;
}
