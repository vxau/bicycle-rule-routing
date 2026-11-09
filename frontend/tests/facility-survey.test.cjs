const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const context = vm.createContext({});
const sourcePath = path.join(__dirname, '../facility-survey.js');
if (fs.existsSync(sourcePath)) vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), context);
const survey = context.FacilitySurvey || {};

test('survey CSV preserves quotes, Japanese, BOM and empty evidence fields', () => {
  assert.equal(typeof survey.toCsv, 'function');
  const csv = survey.toCsv([{
    segment_id: '1|2|0', name: '道路,"A"\n東京', facility_state: 'unknown',
    length_m: 123.4, start_lat: 35, start_lon: 139, end_lat: 35.1, end_lon: 139.1,
    directions: [{ u: '1', v: '2', key: '0', tags: { cycleway: [] } }],
  }], 'dataset-1');
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes('"道路,""A""\n東京"'));
  assert.ok(csv.includes('"dataset-1"'));
  assert.ok(csv.includes('"確認結果","確認日","根拠・資料URL","幅員_m","メモ"'));
  assert.ok(csv.endsWith(',"","","","",""\r\n'));
});

test('spreadsheet formula prefixes in untrusted names are neutralized', () => {
  assert.equal(typeof survey.csvCell, 'function');
  for (const value of ['=1+1', '+SUM(A1)', '-1+2', '@SUM(A1)', '\t=1+1', '\r=1+1', '  =1+1']) {
    assert.ok(survey.csvCell(value).startsWith('"\''), value);
  }
  assert.equal(survey.csvCell(null), '""');
  assert.equal(survey.csvCell(42), '"42"');
});

test('saved selections only restore for the same dataset and existing IDs', () => {
  assert.equal(typeof survey.restoreSelection, 'function');
  const saved = JSON.stringify({ datasetId: 'current', ids: ['a', 'b', 'a', 'removed'] });
  const restored = survey.restoreSelection(saved, 'current', ['a', 'b']);
  assert.deepEqual(Array.from(restored.ids), ['a', 'b']);
  assert.equal(restored.stale, false);
  const stale = survey.restoreSelection(saved, 'changed', ['a', 'b']);
  assert.deepEqual(Array.from(stale.ids), []);
  assert.equal(stale.stale, true);
  for (const invalid of [null, '{bad json', '{}', 'null', '{"datasetId":"current","ids":2}']) {
    assert.deepEqual(Array.from(survey.restoreSelection(invalid, 'current', ['a']).ids), []);
  }
});
