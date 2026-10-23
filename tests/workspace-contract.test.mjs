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
