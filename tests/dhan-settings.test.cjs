const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
function route({ user = {id:'user'}, profileId = '123456', existing = null } = {}) {
 const writes=[]
 const imports={
  'next/server': {NextResponse:{json:(body, options)=>({body,status:options?.status||200})}},
  '@/lib/supabase/server':{createClient:async()=>({auth:{getUser:async()=>({data:{user},error:null})}})},
  '@/lib/convex/server':{convexAdminMutation:async(name,args)=>{writes.push({name,args})}},
  '@/lib/dhan/user-credentials':{getStoredDhanCredentials:async()=>existing},
  '@/lib/dhan/credential-crypto':{encryptDhanCredential:(value,uid,kind)=>'encrypted:'+kind+':'+uid},
 }
 const exports={}
 vm.runInNewContext(ts.transpileModule(fs.readFileSync('app/api/dhan/settings/route.ts','utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020},
 }).outputText,{exports,require:n=>imports[n],Date,Reflect,Array,Number,Error,AbortSignal,
  fetch:async()=>({ok:true,json:async()=>({dhanClientId:profileId,tokenValidity:'31/12/2099 15:30'})}),
 })
 const request=body=>({headers:{get:()=>null},nextUrl:{origin:'http://localhost'},json:async()=>body})
 return {writes,put:body=>exports.PUT(request(body))}
}
const input={dhanClientId:'123456',apiKey:'secret-key',apiSecret:'secret-value',accessToken:'secret-token',pin:'123456',totpSecret:'JBSWY3DPEHPK3PXP',autoRenew:true}
test('settings endpoint rejects unauthenticated users before writing secrets',async()=>{
 const r=route({user:null});assert.equal((await r.put(input)).status,401);assert.equal(r.writes.length,0)
})
test('settings endpoint rejects a token belonging to another account',async()=>{
 const r=route({profileId:'different'});assert.equal((await r.put(input)).status,400);assert.equal(r.writes.length,0)
})
test('settings endpoint encrypts all credentials and returns no secrets',async()=>{
 const r=route();const result=await r.put(input)
 assert.equal(result.status,200);assert.equal(r.writes.length,1)
 const saved=JSON.stringify(r.writes[0].args)
 for(const secret of ['secret-key','secret-value','secret-token','JBSWY3DPEHPK3PXP']) assert.equal(saved.includes(secret),false)
 assert.equal(r.writes[0].args.encryptedPin,'encrypted:pin:user')
 assert.deepEqual(Object.keys(result.body),['success'])
})
test('automatic recovery cannot be enabled without recovery credentials',async()=>{
 const r=route();assert.equal((await r.put({...input,pin:'',totpSecret:''})).status,400);assert.equal(r.writes.length,0)
})
test('six-digit TOTP code is not accepted as the setup secret',async()=>{
 const r=route();assert.equal((await r.put({...input,totpSecret:'123456'})).status,400)
})
