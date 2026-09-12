const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
const output = ts.transpileModule(fs.readFileSync('lib/live-agent-runs.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const sandbox = { exports: {} }
vm.runInNewContext(output, sandbox)
const { reduceLiveRuns, isWireEvent } = sandbox.exports
const event = (request_id, sequence, type = 'stock_agent_thinking') => ({
    type, request_id, rank: 1, sequence, message: `${request_id}-${sequence}`,
    sent_at_utc: '2026-09-11T09:00:00Z',
})

test('parallel rank-one runs never merge and replay is idempotent', () => {
    let runs = reduceLiveRuns({}, event('A', 1))
    runs = reduceLiveRuns(runs, event('B', 1))
    runs = reduceLiveRuns(runs, event('A', 1))
    assert.equal(runs.A.events[1].length, 1)
    assert.equal(runs.B.events[1][0].message, 'B-1')
    runs = reduceLiveRuns(runs, event('B', 2, 'stock_agent_completed'))
    assert.equal(runs.A.state, 'running')
    assert.equal(runs.B.state, 'completed')
})
test('selection and no-trade events do not erase other requests', () => {
    let runs = reduceLiveRuns({}, event('A', 1))
    runs = reduceLiveRuns(runs, { type: 'stock_agent_selection', request_id: 'B', selected: [{ rank: 1, symbol: 'B' }] })
    runs = reduceLiveRuns(runs, { type: 'stock_agent_no_trade', request_id: 'B', reason: 'No capacity' })
    assert.equal(runs.A.events[1].length, 1)
    assert.equal(runs.B.state, 'skipped')
})
test('late replay cannot regress completion or scramble sequence order', () => {
    let runs = reduceLiveRuns({}, event('A', 3, 'stock_agent_completed'))
    runs = reduceLiveRuns(runs, event('A', 1))
    runs = reduceLiveRuns(runs, event('A', 2))
    assert.equal(runs.A.state, 'completed')
    assert.equal(runs.A.events[1].map((item) => item.sequence).join(','), '1,2,3')
})
test('finished notification settles a request without a decision', () => {
    let runs = reduceLiveRuns({}, { type: 'intra_finder_event_accepted', request_id: 'A', event: { symbol: 'TEST' } })
    runs = reduceLiveRuns(runs, { type: 'intra_finder_event_finished', request_id: 'A', status: 'completed' })
    assert.equal(runs.A.state, 'completed')
    assert.equal(runs.A.events[1].at(-1).type, 'stock_agent_no_trade')
})
test('retention bounds finished history without dropping active runs', () => {
    let runs = reduceLiveRuns({}, event('active', 1))
    for (let i = 0; i < 80; i++) runs = reduceLiveRuns(runs, event(`done-${i}`, 1, 'stock_agent_completed'))
    assert.equal(Object.keys(runs).length, 61)
    assert.equal(runs.active.state, 'running')
})
test('reject malformed wire identity and rank', () => {
    for (const value of [null, {}, { type: 4 }, { type: 'stock_agent_started', rank: -1 }, { type: 'stock_agent_started', request_id: {} }]) assert.equal(isWireEvent(value), false)
    assert.equal(isWireEvent(event('A', 1)), true)
})
test('legacy unscoped selection replaces only its own serial board', () => {
    let runs = reduceLiveRuns({}, event('A', 1))
    runs = reduceLiveRuns(runs, { type: 'stock_agent_completed', rank: 1 })
    runs = reduceLiveRuns(runs, { type: 'stock_agent_selection', selected: [{rank: 1, symbol: 'NEW'}] })
    assert.equal(runs.legacy.state, 'running')
    assert.equal(runs.legacy.events[1].length, 1)
    assert.equal(runs.A.events[1].length, 1)
})
test('a later second agent keeps its batch running until every agent finishes', () => {
    let runs = reduceLiveRuns({}, event('A', 1, 'stock_agent_completed'))
    runs = reduceLiveRuns(runs, {...event('A', 1, 'stock_agent_started'), rank: 2})
    assert.equal(runs.A.state, 'running')
    runs = reduceLiveRuns(runs, {...event('A', 2, 'stock_agent_completed'), rank: 2})
    assert.equal(runs.A.state, 'completed')
})
