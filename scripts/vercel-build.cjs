const { spawnSync } = require('node:child_process')
const path = require('node:path')

// A production frontend must not publish routes whose Convex functions are missing.
const key = process.env.CONVEX_DEPLOY_KEY || process.env.CONVEX_ADMIN_KEY
const production = process.env.VERCEL_ENV === 'production'
if (production && !key) {
    console.error('Production build requires CONVEX_DEPLOY_KEY or CONVEX_ADMIN_KEY on Vercel.')
    process.exit(1)
}
const executable = production ? 'convex/bin/main.js' : 'next/dist/bin/next'
const args = production ? ['deploy', '--typecheck', 'enable', '--cmd', 'npm run build'] : ['build']
const result = spawnSync(process.execPath, [path.resolve('node_modules', executable), ...args], {
    stdio: 'inherit',
    env: { ...process.env, ...(production ? { CONVEX_DEPLOY_KEY: key } : {}) },
})
if (result.error) console.error('Build command could not start:', result.error.message)
process.exit(result.status ?? 1)
