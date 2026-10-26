# Offline math renderer

KaTeX 0.19.1 from the official npm package:
https://registry.npmjs.org/katex/-/katex-0.19.1.tgz

Tarball integrity (verified during vendoring):
`sha512-jG8uKntjSEcm2EpQOh0XturpPuuC9r3Sq5HLHdsFdWZT27E672SF19QEi+of0/YeOy15lDgRhKvr5614uRrEfA==`

Only `katex.min.js`, `katex.min.css`, `contrib/auto-render.min.js`,
unmodified WOFF2 fonts, and the MIT license were copied. CSS removes fallback
references to WOFF/TTF files, which are not bundled. The font name tables of
all matching upstream TTF files identify SIL OFL 1.1 and Reserved Font Names;
their copyright notices and full OFL text are in `FONTS-LICENSE.txt`.

`index.html`, `viewer.css`, `viewer.js` belong to Study Agent. There are no
CDNs or runtime downloads. User text is assigned using `textContent`; KaTeX
runs with `trust: false`, `maxExpand: 200`, `maxSize: 20`. CSP denies network
connections and images; WKNavigationDelegate denies navigation outside the
bundled entry page. HTML is never parsed from source excerpts. Text inside
backtick/tilde fences and inline backtick spans stays verbatim. Math renders with HTML and MathML.
