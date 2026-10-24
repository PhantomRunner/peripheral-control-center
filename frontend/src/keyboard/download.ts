export function download(name: string, content: string | Uint8Array, type: string) {
  const blob = new Blob([typeof content === 'string' ? content : new Uint8Array(content)], { type });
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  // Leave time for the browser to start the download before revoking its local URL.
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
