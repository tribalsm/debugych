import{test}from'node:test';import assert from'node:assert/strict';import{normalizeSize,petDimensions}from'../web/sizing.js';
test('custom size clamps invalid persisted values',()=>{assert.equal(normalizeSize('bad'),160);assert.equal(normalizeSize(99),100);assert.equal(normalizeSize(999),260);assert.equal(normalizeSize(159.6),160)});
test('size presets and custom preserve proportions at supported DPI',()=>{for(const h of[100,120,160,200,260])for(const dpi of[1,1.25,1.5,2]){const d=petDimensions(h,dpi);assert.equal(d.height,Math.round(h*dpi));assert.ok(Math.abs(d.width/d.height-5/6)<.006)}});

import fs from'node:fs';
test('sprite resolution covers largest size at 200 percent DPI with real alpha edges',()=>{const m=JSON.parse(fs.readFileSync(new URL('../web/assets/manifest.json',import.meta.url)));assert.ok(m.height>=260*2);const alpha=JSON.parse(fs.readFileSync(new URL('../evidence/sprites.json',import.meta.url)));assert.ok(alpha.checks.every(c=>c.transparentCorners));assert.ok(alpha.alpha.every(c=>c.transparent>0&&c.semTransparent>0&&c.opaque>0))});
