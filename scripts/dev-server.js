const { rmSync } = require('fs')
const { join } = require('path')
const { spawn } = require('child_process')

const root = join(__dirname, '..')
const nextCache = join(root, '.next')
const userArgs = process.argv.slice(2)
const hasPortArg = userArgs.includes('-p') || userArgs.includes('--port')
const nextArgs = ['dev', ...userArgs]

if (!hasPortArg) {
  nextArgs.push('-p', process.env.PORT || '3000')
}

try {
  rmSync(nextCache, { recursive: true, force: true })
  console.log('Cleared stale .next cache before starting dev server.')
} catch (error) {
  console.warn(`Could not clear .next cache: ${error.message}`)
}

const nextCli = require.resolve('next/dist/bin/next')
const child = spawn(process.execPath, [nextCli, ...nextArgs], {
  cwd: root,
  stdio: 'inherit',
  shell: false,
  env: {
    ...process.env,
    WATCHPACK_POLLING: process.env.WATCHPACK_POLLING || 'true',
    CHOKIDAR_USEPOLLING: process.env.CHOKIDAR_USEPOLLING || 'true',
  },
})

child.on('exit', (code, signal) => {
  if (signal) {
    process.exit(1)
    return
  }
  process.exit(code ?? 0)
})
