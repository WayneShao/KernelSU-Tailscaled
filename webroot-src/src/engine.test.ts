import { describe, expect, it } from 'vitest';
import { parseEngineStatus } from './engine';
import { renderEngineUpdate } from './render';

describe('engine updates', () => {
  it('rejects unknown policy', () => {
    expect(() => parseEngineStatus('{"current":"1.104.4","latest":"","staged":"","policy":"typo"}')).toThrow();
  });
  it('explains compatibility pin and hides engine replacement actions', () => {
    const root = document.createElement('div');
    renderEngineUpdate(root, parseEngineStatus('{"current":"1.104.4","latest":"1.106.0","staged":"1.106.0","policy":"bundled-compatibility"}'));
    expect(root.querySelector('[data-action=engine-prepare]')).toBeNull();
    expect(root.querySelector('[data-action=engine-apply]')).toBeNull();
    expect(root.textContent).toContain('兼容性');
    expect(root.querySelector('[data-action=engine-check]')).not.toBeNull();
  });
  it('rejects unexpected version content', () => {
    expect(() => parseEngineStatus('{"current":"1.104.2","latest":"1.2.3;id","staged":""}')).toThrow();
  });
  it('only offers applying a verified staged version', () => {
    const root = document.createElement('div');
    renderEngineUpdate(root, parseEngineStatus('{"current":"1.104.2","latest":"1.106.0","staged":""}'));
    expect(root.querySelector('[data-action=engine-prepare]')).not.toBeNull();
    expect(root.querySelector('[data-action=engine-apply]')).toBeNull();
    renderEngineUpdate(root, parseEngineStatus('{"current":"1.104.2","latest":"1.106.0","staged":"1.106.0"}'));
    expect(root.querySelector('[data-action=engine-apply]')).not.toBeNull();
  });
});
