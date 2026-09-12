const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')

function worker(fetch) {
    const handlers = new Map()
    const cached = []
    const removed = []
    let activated = false
    vm.runInNewContext(fs.readFileSync('public/sw.js', 'utf8'), {
        URL, Response, fetch,
        self: { location: { origin: 'https://example.test' }, addEventListener: (name, handler) => handlers.set(name, handler),
            clients: { claim: async () => {} }, skipWaiting: () => { activated = true } },
        caches: { open: async () => ({ add: async (url) => cached.push(url) }),
            match: async () => new Response('offline'),
            keys: async () => ['polycognition-offline-v0', 'another-app-cache', 'polycognition-offline-v1'],
            delete: async (key) => removed.push(key) },
    })
    return { handlers, cached, removed, activated: () => activated }
}
test('only the public offline page is precached; updates require explicit activation', async () => {
    const instance = worker(async () => new Response('network'))
    await new Promise((resolve, reject) => instance.handlers.get('install')({ waitUntil: (promise) => promise.then(resolve, reject) }))
    assert.deepEqual(instance.cached, ['/offline.html'])
    assert.equal(instance.activated(), false)
    instance.handlers.get('message')({ data: { type: 'ACTIVATE_UPDATE' } })
    assert.equal(instance.activated(), true)
    await new Promise((resolve, reject) => instance.handlers.get('activate')({ waitUntil: (promise) => promise.then(resolve, reject) }))
    assert.deepEqual(instance.removed, ['polycognition-offline-v0'])
})
test('API calls, authentication and mutations bypass the worker', () => {
    const instance = worker(() => { throw Error('unexpected fetch') })
    for (const [path, method, mode] of [['/api/dhan/orders','GET','navigate'], ['/auth/signout','GET','navigate'], ['/dashboard','POST','navigate'], ['/api/ai-trading/config','POST','cors']]) {
        instance.handlers.get('fetch')({ request: { url: `https://example.test${path}`, method, mode }, respondWith: () => assert.fail('intercepted private operation') })
    }
})
test('failed navigation shows the offline screen and successful navigation stays fresh', async () => {
    for (const online of [true, false]) {
        const instance = worker(async () => { if (!online) throw Error('offline'); return new Response('fresh account data') })
        let response
        instance.handlers.get('fetch')({ request: { url: 'https://example.test/dashboard', method: 'GET', mode: 'navigate' }, respondWith: (promise) => { response = promise } })
        assert.equal(await (await response).text(), online ? 'fresh account data' : 'offline')
        assert.deepEqual(instance.cached, [])
    }
})
