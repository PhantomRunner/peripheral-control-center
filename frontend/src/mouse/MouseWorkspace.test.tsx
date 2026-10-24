import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { MouseWorkspace } from './MouseWorkspace';
import { mouse } from '../test/fixtures';

it('keeps drafts across accessible tabs without sending requests', () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  render(<MouseWorkspace device={mouse} stale={false} onUpdated={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Current stage DPI (draft)'), { target: { value:'1200' } });
  fireEvent.click(screen.getByRole('tab', { name:'Sensor' }));
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  fireEvent.keyDown(screen.getByRole('tab', { name:'Sensor' }), { key:'Home' });
  expect(screen.getByLabelText('Current stage DPI (draft)')).toHaveValue(1200);
  expect(screen.getByRole('tab', { name:'DPI & polling' })).toHaveFocus();
  expect(fetch).not.toHaveBeenCalled();
});
