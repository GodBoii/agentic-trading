const { rmSync } = require('fs')
const { join } = require('path')
const { spawn } = require('child_process')
const net = require('net')

const root = join(__dirname, '..')
const nextCache = join(root, '.next')
const userArgs = process.argv.slice(2)
const nextArgs = ['dev', ...userArgs]
const port = resolvePort(userArgs)

if (!hasPortArg(userArgs)) {
  nextArgs.push('-p', port)
}

main().catch((error) => {
  console.error(error.message || error)
  process.exit(1)
})

async function main() {
  if (await isPortInUse(port)) {
    console.error(`Port ${port} is already in use. Stop the existing dev server before running npm run dev again.`)
    process.exit(1)
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
}

function hasPortArg(args) {
  return args.some((arg) => arg === '-p' || arg === '--port' || arg.startsWith('--port='))
}

function resolvePort(args) {
  const defaultPort = process.env.PORT || '3000'
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index]
    if ((arg === '-p' || arg === '--port') && args[index + 1]) {
      return args[index + 1]
    }
    if (arg.startsWith('--port=')) {
      return arg.slice('--port='.length)
    }
  }
  return defaultPort
}

function isPortInUse(portToCheck) {
  return Promise.all([
    canConnect('127.0.0.1', portToCheck),
    canConnect('::1', portToCheck),
  ]).then((results) => results.some(Boolean))
}

function canConnect(host, portToCheck) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port: Number(portToCheck), timeout: 400 })
    socket.once('connect', () => {
      socket.destroy()
      resolve(true)
    })
    socket.once('timeout', () => {
      socket.destroy()
      resolve(false)
    })
    socket.once('error', () => {
      resolve(false)
    })
  })
}
