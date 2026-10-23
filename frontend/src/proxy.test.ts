// @vitest-environment node
import { expect, it } from 'vitest';
import config from '../vite.config';

it('preserves the browser Host so backend Origin checks work through the local proxy', () => {
  const proxy = config.server?.proxy?.['/api'];
  expect(typeof proxy).toBe('object');
  expect(proxy).toMatchObject({ target: 'http://127.0.0.1:8000', changeOrigin: false });
});
