const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')

function loadModule(file, imports) {
    const exports = {}
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    }).outputText, { exports, require: name => {
        if (!(name in imports)) throw new Error('Unexpected import: ' + name)
        return imports[name]
    }, Date, Error })
    return exports
}

const validators = new Proxy({}, { get: () => () => ({}) })
const mutations = loadModule('convex/dhanCredentials.ts', {
    'convex/values': { v: validators },
    './_generated/server': { internalMutation: x => x, internalQuery: x => x },
})

function database(rows) {
    return { db: {
        query() {
            let user
            return { withIndex(_name, fn) { fn({ eq(_field, value) { user = value } }); return this },
                async unique() { return rows.find(r => r.supabaseUserId === user) || null },
                async collect() { return rows },
            }
        },
        async patch(id, patch) { Object.assign(rows.find(r => r._id === id), patch) },
        async insert(_table, row) { rows.push({ _id: 'new', ...row }); return 'new' },
        async delete(id) { rows.splice(rows.findIndex(r => r._id === id), 1) },
    } }
}
const row = () => ({ _id: '1', supabaseUserId: 'user', dhanClientId: '123456', updatedAt: 'revision-1' })
const lease = { supabaseUserId: 'user', expectedUpdatedAt: 'revision-1', owner: 'worker-a' }

test('only one worker can hold a credential lease', async () => {
    const rows = [row()], ctx = database(rows)
    assert.equal(await mutations.acquireLease.handler(ctx, lease), true)
    assert.equal(await mutations.acquireLease.handler(ctx, { ...lease, owner: 'worker-b' }), false)
})

test('stale worker cannot publish over newer credentials', async () => {
    const rows = [{ ...row(), updatedAt: 'revision-2', leaseOwner: 'worker-a', leaseUntil: Date.now() + 60000 }]
    assert.equal(await mutations.finishCheck.handler(database(rows), { ...lease, authStatus: 'ready', encryptedAccessToken: 'stale' }), false)
    assert.equal(rows[0].encryptedAccessToken, undefined)
})

test('expired lease cannot publish', async () => {
    const rows = [{ ...row(), leaseOwner: 'worker-a', leaseUntil: Date.now() - 1 }]
    assert.equal(await mutations.finishCheck.handler(database(rows), { ...lease, authStatus: 'ready' }), false)
})

test('disconnect prevents an in-flight worker from recreating credentials', async () => {
    assert.equal(await mutations.finishCheck.handler(database([]), { ...lease, authStatus: 'ready' }), false)
})

test('status-only checks preserve credential revision and clear old errors', async () => {
    const rows = [{ ...row(), leaseOwner: 'worker-a', leaseUntil: Date.now() + 60000, authError: 'old' }]
    assert.equal(await mutations.finishCheck.handler(database(rows), { ...lease, authStatus: 'ready' }), true)
    assert.equal(rows[0].updatedAt, 'revision-1')
    assert.equal(rows[0].authError, undefined)
    assert.equal(rows[0].leaseOwner, undefined)
})

test('credential edit cannot race a renewal', async () => {
    const rows = [{ ...row(), leaseUntil: Date.now() + 60000 }]
    await assert.rejects(mutations.saveSettings.handler(database(rows), {
        supabaseUserId: 'user', dhanClientId: '123456', expectedUpdatedAt: 'revision-1',
        encryptedApiKey: 'key', encryptedApiSecret: 'secret', autoRenew: true, clearRecovery: false,
    }), /Credentials changed/)
})

test('duplicate Dhan account cannot bind to another website user', async () => {
    await assert.rejects(mutations.saveSettings.handler(database([row()]), {
        supabaseUserId: 'other', dhanClientId: '123456', encryptedApiKey: 'key', encryptedApiSecret: 'secret',
        autoRenew: false, clearRecovery: false,
    }), /already connected/)
})

test('stale browser callback cannot replace a renewed token', async () => {
    const rows = [{ ...row(), updatedAt: 'revision-2' }]
    await assert.rejects(mutations.setToken.handler(database(rows), {
        supabaseUserId: 'user', dhanClientId: '123456', expectedUpdatedAt: 'revision-1',
        encryptedAccessToken: 'stale', tokenExpiresAt: 'later', updatedAt: 'new',
    }), /Credentials changed/)
})

test('blank recovery fields preserve secrets; explicit removal clears both', async () => {
    const rows = [{ ...row(), encryptedPin: 'pin-ciphertext', encryptedTotpSecret: 'totp-ciphertext' }]
    const input = { supabaseUserId: 'user', dhanClientId: '123456', expectedUpdatedAt: 'revision-1', encryptedApiKey: 'key', encryptedApiSecret: 'secret', autoRenew: false, clearRecovery: false }
    await mutations.saveSettings.handler(database(rows), input)
    assert.equal(rows[0].encryptedPin, 'pin-ciphertext')
    await mutations.saveSettings.handler(database(rows), { ...input, expectedUpdatedAt: rows[0].updatedAt, clearRecovery: true })
    assert.equal(rows[0].encryptedPin, undefined)
    assert.equal(rows[0].encryptedTotpSecret, undefined)
})
test('successful consent publication requires the lease owner', async () => {
    const rows = [{ ...row(), leaseOwner: 'worker-a', leaseUntil: Date.now() + 60000 }]
    await mutations.setToken.handler(database(rows), {
        ...lease, dhanClientId: '123456', encryptedAccessToken: 'replacement', tokenExpiresAt: 'later', updatedAt: 'revision-2',
    })
    assert.equal(rows[0].encryptedAccessToken, 'replacement')
    assert.equal(rows[0].leaseOwner, undefined)
    assert.equal(rows[0].tokenSource, 'consent')
})
