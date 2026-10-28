'use strict';
// A deliberately small Markdown subset. No HTML parsing, links, images or remote resources.
window.renderStudyContent = function (text, dark) {
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  const root = document.getElementById('content');
  root.replaceChildren();
  const protectedSpans = [];
  let prefix = '\uE000STUDY';
  while (text.includes(prefix)) prefix += 'X';
  const suffix = '\uE001';
  function protect(type, value, display = false) {
    const index = protectedSpans.push({type, value, display}) - 1;
    return prefix + index + suffix;
  }
  function escaped(source, index) {
    let count = 0;
    for (let pos = index - 1; pos >= 0 && source[pos] === '\\'; pos--) count++;
    return count % 2 === 1;
  }
  function closing(source, delimiter, start, singleDollar = false) {
    let index = start;
    while ((index = source.indexOf(delimiter, index)) >= 0) {
      if (!escaped(source, index) && (!singleDollar || (source[index - 1] !== '$' && source[index + 1] !== '$'))) return index;
      index += delimiter.length;
    }
    return -1;
  }
  // Protect code and entire math expressions before any Markdown transformation.
  // Multiline display math becomes a single token, so blank lines and underscores stay intact.
  function protectContent(source) {
    let output = '';
    for (let index = 0; index < source.length;) {
      const rest = source.slice(index);
      if (index === 0 || source[index - 1] === '\n') {
        const opening = rest.match(/^ {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$)/);
        if (opening) {
          const fence = opening[1];
          const tail = rest.slice(opening[0].length);
          const end = new RegExp('^ {0,3}' + fence[0] + '{' + fence.length + ',}[ \\t]*(?:\\n|$)', 'm').exec(tail);
          const code = end ? tail.slice(0, end.index).replace(/\n$/, '') : tail;
          output += protect('fence', code) + '\n';
          index += opening[0].length + (end ? end.index + end[0].length : tail.length);
          continue;
        }
      }
      // Indented code starts a block only at the document start or after a blank
      // line. A four-space continuation of an existing paragraph stays prose.
      if ((index === 0 || source[index - 1] === '\n')
          && /^(?: {4}|\t)/.test(rest)
          && (index === 0 || /(?:^|\n)[ \t]*\n$/.test(source.slice(0, index)))) {
        const lines = [];
        let cursor = index;
        while (cursor < source.length) {
          const nextBreak = source.indexOf('\n', cursor);
          const end = nextBreak < 0 ? source.length : nextBreak + 1;
          const line = source.slice(cursor, end).replace(/\n$/, '');
          if (/^(?: {4}|\t)/.test(line)) lines.push(line.replace(/^(?: {4}|\t)/, ''));
          else if (!line.trim()) lines.push('');
          else break;
          cursor = end;
        }
        output += protect('fence', lines.join('\n').replace(/\n+$/, '')) + '\n';
        index = cursor;
        continue;
      }
      if (source[index] === '`' && !escaped(source, index)) {
        const run = rest.match(/^`+/)[0];
        const runs = [...rest.slice(run.length).matchAll(/`+/g)];
        const end = runs.find(candidate => candidate[0].length === run.length);
        if (end) {
          output += protect('code', rest.slice(run.length, run.length + end.index));
          index += run.length + end.index + run.length;
          continue;
        }
      }
      const delimiter = !escaped(source, index) && ['$$', '\\[', '\\(', '$'].find(value => rest.startsWith(value));
      if (delimiter) {
        const right = delimiter === '\\[' ? '\\]' : delimiter === '\\(' ? '\\)' : delimiter;
        const end = closing(source, right, index + delimiter.length, delimiter === '$');
        const content = end < 0 ? '' : source.slice(index + delimiter.length, end);
        if (content && (delimiter !== '$' || !content.includes('\n'))) {
          output += protect('math', content, delimiter === '$$' || delimiter === '\\[');
          index = end + right.length;
          continue;
        }
      }
      if (source[index] === '\\' && /[\\`*_{}\[\]()#+.!|>$~-]/.test(source[index + 1] || '')) {
        output += protect('literal', source[index + 1]);
        index += 2;
        continue;
      }
      output += source[index++];
    }
    return output;
  }
  const masked = protectContent(text);
  const tokenPattern = prefix + '(\\d+)' + suffix;
  function appendToken(parent, index) {
    const token = protectedSpans[index];
    const node = document.createElement(token.type === 'fence' ? 'pre' : token.type === 'code' ? 'code' : 'span');
    if (token.type === 'math') {
      katex.render(token.value, node, {displayMode:token.display,
        throwOnError:false, trust:false, strict:'ignore', maxExpand:200, maxSize:20,
        output:'htmlAndMathml', errorColor:dark ? '#ffb5a6' : '#a32616'});
    } else node.textContent = token.value;
    parent.appendChild(node);
  }
  function inline(parent, source, depth = 0) {
    // Tokens have priority over emphasis; code and TeX contents are never re-parsed.
    const pattern = new RegExp(tokenPattern + '|(\\*\\*|__)(?=\\S)(.+?\\S|\\S)\\2|(?<![\\w])([*_])(?=\\S)(.+?\\S|\\S)\\4(?![\\w])', 'gs');
    let cursor = 0;
    for (const match of source.matchAll(pattern)) {
      parent.appendChild(document.createTextNode(source.slice(cursor, match.index)));
      if (match[1] !== undefined) appendToken(parent, Number(match[1]));
      else {
        const node = document.createElement(match[2] ? 'strong' : 'em');
        const content = match[3] || match[5];
        if (depth < 12) inline(node, content, depth + 1);
        else node.textContent = content;
        parent.appendChild(node);
      }
      cursor = match.index + match[0].length;
    }
    parent.appendChild(document.createTextNode(source.slice(cursor)));
  }
  function element(parent, tag, value) {
    const node = document.createElement(tag);
    if (value !== undefined) inline(node, value);
    parent.appendChild(node);
    return node;
  }
  function cells(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(value => value.trim());
  }
  function isTableDivider(line) {
    const parts = cells(line);
    return parts.length > 1 && parts.every(value => /^:?-{3,}:?$/.test(value));
  }
  const standaloneToken = new RegExp('^' + tokenPattern + '$');
  function blocks(parent, source, depth = 0) {
    const lines = source.split('\n');
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) { index++; continue; }
      const token = line.trim().match(standaloneToken);
      if (token && protectedSpans[Number(token[1])].type === 'fence') {
        appendToken(parent, Number(token[1])); index++; continue;
      }
      const heading = line.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*$/);
      if (heading) { element(parent, 'h' + heading[1].length, heading[2]); index++; continue; }
      if (index + 1 < lines.length && line.includes('|') && isTableDivider(lines[index + 1])) {
        const wrapper = element(parent, 'div'); wrapper.className = 'table-scroll';
        const table = element(wrapper, 'table');
        const row = element(element(table, 'thead'), 'tr');
        const headers = cells(line);
        headers.forEach(value => element(row, 'th', value));
        const body = element(table, 'tbody');
        index += 2;
        while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
          const row = element(body, 'tr');
          const values = cells(lines[index++]);
          headers.forEach((_, col) => element(row, 'td', values[col] || ''));
        }
        continue;
      }
      if (/^ {0,3}> ?/.test(line) && depth < 12) {
        const quote = [];
        while (index < lines.length && /^ {0,3}> ?/.test(lines[index])) quote.push(lines[index++].replace(/^ {0,3}> ?/, ''));
        blocks(element(parent, 'blockquote'), quote.join('\n'), depth + 1);
        continue;
      }
      const firstItem = line.match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
      if (firstItem) {
        const ordered = /^\d/.test(firstItem[1]);
        const list = element(parent, ordered ? 'ol' : 'ul');
        if (ordered) list.start = parseInt(firstItem[1], 10);
        while (index < lines.length) {
          const item = lines[index].match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
          if (!item || /^\d/.test(item[1]) !== ordered) break;
          element(list, 'li', item[2]); index++;
        }
        continue;
      }
      const paragraph = [line]; index++;
      while (index < lines.length && lines[index].trim()
          && !/^\s*(?:#{1,6}\s|>\s?|[-+*]\s|\d+[.)]\s)/.test(lines[index])
          && !standaloneToken.test(lines[index].trim())
          && !(index + 1 < lines.length && isTableDivider(lines[index + 1]))) paragraph.push(lines[index++]);
      element(parent, 'p', paragraph.join('\n'));
    }
  }
  blocks(root, masked);
};
new ResizeObserver(() => {
  const handler = window.webkit?.messageHandlers?.mathHeight;
  if (handler) handler.postMessage(Math.ceil(document.getElementById('content').getBoundingClientRect().height));
}).observe(document.getElementById('content'));
