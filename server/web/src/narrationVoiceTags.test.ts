import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { NarrationVoiceTags } from './NarrationVoiceTags';

describe('NarrationVoiceTags', () => {
  it('shows delivery and inline pauses from the actual TTS text', () => {
    const html = renderToStaticMarkup(createElement(NarrationVoiceTags, { text: '[Warm, calm narration, slow measured delivery] 語ります。[short pause] 続きます。' }));
    expect(html).toContain('温かく落ち着いた、ゆっくりした語り');
    expect(html).toContain('短い間');
    expect(html).not.toContain('続きます。');
  });
  it('reflects edited text and does not show tags that were removed', () => {
    const html = renderToStaticMarkup(createElement(NarrationVoiceTags, { text: '[thoughtful] 新しい文です。' }));
    expect(html).toContain('thoughtful');
    expect(html).not.toContain('短い間');
  });
  it('clearly distinguishes missing tags from intentional silence', () => {
    expect(renderToStaticMarkup(createElement(NarrationVoiceTags, { text: '普通の文です。' }))).toContain('タグ未指定');
    expect(renderToStaticMarkup(createElement(NarrationVoiceTags, { text: '[calm] 古い文', silent: true }))).toBe('');
  });
});
