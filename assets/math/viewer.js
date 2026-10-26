'use strict';
// User content is inserted exclusively as text. KaTeX's trusted commands are disabled.
window.renderStudyContent = function (text, dark) {
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  const root = document.getElementById('content');
  root.replaceChildren();
  let fence = null, buffer = [];
  function appendInlineContent(node, text) {
    const ticks = [...text.matchAll(/`+/g)];
    let cursor = 0;
    for (let index = 0; index < ticks.length; index++) {
      const opening = ticks[index];
      let backslashes = 0;
      for (let pos = opening.index - 1; pos >= 0 && text[pos] === '\\'; pos--) backslashes++;
      if (backslashes % 2) continue;
      const closingIndex = ticks.findIndex((run, next) => next > index && run[0].length === opening[0].length);
      if (closingIndex < 0) continue;
      const closing = ticks[closingIndex];
      node.appendChild(document.createTextNode(text.slice(cursor, opening.index)));
      const code = document.createElement('code');
      code.textContent = text.slice(opening.index + opening[0].length, closing.index);
      node.appendChild(code);
      cursor = closing.index + closing[0].length;
      index = closingIndex;
    }
    node.appendChild(document.createTextNode(text.slice(cursor)));
  }
  function flush(code) {
    if (!buffer.length) return;
    const node = document.createElement(code ? 'pre' : 'div');
    const content = buffer.join('\n');
    if (code) node.textContent = content;
    else appendInlineContent(node, content);
    root.appendChild(node); buffer = [];
    if (!code) renderMathInElement(node, {
      delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},
        {left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}],
      throwOnError:false, trust:false, strict:'ignore', maxExpand:200, maxSize:20,
      output:'htmlAndMathml', errorColor:dark ? '#ffb5a6' : '#a32616'
    });
  }
  for (const line of text.split('\n')) {
    const marker = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (marker && (!fence || (marker[1][0] === fence[0] && marker[1].length >= fence.length))) {
      if (fence) { buffer.push(line); flush(true); fence = null; }
      else { flush(false); fence = marker[1]; buffer.push(line); }
    } else buffer.push(line);
  }
  flush(Boolean(fence));
};
new ResizeObserver(() => window.webkit.messageHandlers.mathHeight.postMessage(
  Math.ceil(document.getElementById('content').getBoundingClientRect().height)
)).observe(document.getElementById('content'));
