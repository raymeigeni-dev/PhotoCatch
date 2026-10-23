import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';

const html=readFileSync(new URL('../frontend/3d-workspace.html',import.meta.url),'utf8');
const marker='<script type="module">';
const start=html.indexOf(marker);
const end=html.lastIndexOf('</script>');
const script=start>=0&&end>start?html.slice(start+marker.length,end):null;

test('workspace module script parses as JavaScript module',()=>{
  assert.ok(script,'module script must exist');
  const r=spawnSync(process.execPath,['--check','--input-type=module'],{input:script,encoding:'utf8'});
  assert.equal(r.status,0,r.stderr||r.stdout||'module syntax check failed');
});
test('interactive editing controls are wired to real editing handlers',()=>{
  for(const id of ['boxSelect','lassoSelect','brushSelect','polySelect','dragVertex','extrudeRegion','sculptMode','repairMesh','undo','redo','saveScene'])
    assert.ok(html.includes('id="'+id+'"'),`missing control: ${id}`);
  assert.match(html,/selectedVertices=chosen/,'region selection must retain multiple selected vertices');
  assert.match(html,/indices:selectedVertices\.length\?selectedVertices/,'vertex drag must move the complete selection');
  assert.match(html,/sculptStroke=\{mesh:selectedPart\}/,'sculpt button must enter a stroke state');
  assert.match(html,/sculpt\(core,/,'sculpt stroke must call mesh sculpt operation');
  assert.match(html,/return mergeVertices\(m,1e-5\)/,'non-indexed geometry must be welded for adjacency operations');
});

test('topology edits fail closed before conversion when geometry metadata is unsupported',()=>{
  assert.match(html,/function assertTopologyEditable\\(g\\)/,'must centralize the geometry safety gate');
  assert.match(html,/const extra=Object\\.keys\\(g\\.attributes\\|\\|\\{\\}\\)\\.filter/,'must detect non-position attributes such as UVs and colors');
  assert.match(html,/const hasGroups=Array\\.isArray\\(g\\.groups\\)&&g\\.groups\\.length>0/,'must detect material groups');
  assert.match(html,/const hasMorph=/,'must detect morph attributes');
  assert.match(html,/hasPartialDrawRange/,'must detect partial draw ranges');
  assert.match(html,/function geometryToCore\\(g\\)\\{assertTopologyEditable\\(g\\)/,'must guard before welding/converting the source geometry');
  assert.match(html,/为防止数据丢失，已阻止此网格的拓扑编辑/,'must fail closed rather than silently drop data');
});
