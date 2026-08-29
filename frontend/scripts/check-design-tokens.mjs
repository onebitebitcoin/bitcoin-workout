#!/usr/bin/env node
/**
 * 디자인 토큰 규칙 검사기.
 *
 * 왜 ESLint 규칙이 아니라 별도 스크립트인가: 여기서 막으려는 것은 JSX 구조가 아니라
 * className 문자열의 내용이다. ESLint 코어로는 문자열 안을 볼 수 없고, 이것만을 위해
 * tailwind 플러그인을 의존성에 추가할 이유도 없다.
 *
 * 예외를 두려면 해당 줄이나 바로 윗줄에 `design-token-exempt: <이유>` 주석을 단다.
 * 예외는 코드 안에 이유와 함께 남고, 이 파일에는 목록을 두지 않는다.
 */
/* global console, process */
import { readFileSync, globSync } from 'node:fs'
import path from 'node:path'

const RULES = [
  {
    id: 'arbitrary-font-size',
    re: /text-\[\d+px\]/g,
    msg: '임의 글자 크기. text-display / title / lead / body / label / eyebrow 중에서 고른다.',
  },
  {
    id: 'legacy-font-scale',
    re: /\btext-(xs|sm|base|lg|xl|2xl|3xl|4xl|5xl)\b/g,
    msg: '구 타입 스케일. text-display / title / lead / body / label / eyebrow 로 바꾼다.',
  },
  {
    id: 'palette-escape',
    re: /\b(?:bg|text|border|ring|from|via|to|fill|stroke|placeholder|divide|outline|shadow|decoration|accent)-(?:zinc|gray|slate|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/g,
    msg: 'Tailwind 팔레트 직접 호출. --accent / --danger / --success / --warning / --lightning / theme-* 토큰을 쓴다.',
  },
  {
    id: 'legacy-radius',
    re: /\brounded-(sm|md|lg|xl|2xl|3xl|full)\b/g,
    msg: '라운드는 rounded-card(면)와 rounded-pill(원형) 두 종뿐이다.',
  },
  {
    id: 'half-step-spacing',
    re: /\b(?:gap-x|gap-y|gap|space-x|space-y|px|py|pt|pb|pl|pr|p|mx|my|mt|mb|ml|mr|m)-\d+\.5\b/g,
    msg: '반 칸 간격. 4px 격자 위 정수 단계만 쓴다 (1·2·3·4·5·6·8).',
  },
  {
    id: 'removed-token',
    re: /\btheme-subtle\b/g,
    msg: '--text-subtle 은 삭제됐다. theme-muted 를 쓰고, 위계는 크기와 굵기로 만든다.',
  },
  {
    id: 'legacy-shadow',
    // shadow-sm/md/lg/xl/2xl/inner, 임의값 shadow-[...], bare shadow 를 잡는다.
    // 앞뒤로 [\w-]가 아닌지 직접 확인해야 한다: 단순 \b 는 하이픈 앞에서도 성립해서
    // drop-shadow(별개의 filter 유틸리티)의 "shadow" 부분까지 잘못 잡거나,
    // shadow-float/shadow-pop(새 토큰)의 "shadow" 부분만 떼어 잘못 잡을 수 있다.
    re: /(?<![\w-])shadow(?:-(?:sm|md|lg|xl|2xl|inner)|-\[[^\]]*\])?(?![\w-])/g,
    msg: '구 그림자 스케일. shadow-float(큰 면: 모달·시트·FAB) 또는 shadow-pop(작은 면: 드롭다운·토스트·배지)으로 바꾼다.',
  },
]

const EXEMPT = /design-token-exempt/

const files = globSync('src/**/*.{ts,tsx}', { cwd: process.cwd() })
const violations = []

for (const rel of files) {
  const lines = readFileSync(path.join(process.cwd(), rel), 'utf8').split('\n')
  lines.forEach((line, i) => {
    if (EXEMPT.test(line) || (i > 0 && EXEMPT.test(lines[i - 1]))) return
    for (const rule of RULES) {
      rule.re.lastIndex = 0
      const found = [...line.matchAll(rule.re)].map((m) => m[0])
      if (found.length > 0) {
        violations.push({ file: rel, line: i + 1, rule, found: [...new Set(found)] })
      }
    }
  })
}

if (violations.length === 0) {
  console.log(`디자인 토큰 규칙 OK — ${files.length}개 파일, 위반 0건`)
  process.exit(0)
}

const byRule = new Map()
for (const v of violations) {
  if (!byRule.has(v.rule.id)) byRule.set(v.rule.id, { rule: v.rule, items: [] })
  byRule.get(v.rule.id).items.push(v)
}

console.error(`\n디자인 토큰 규칙 위반 ${violations.length}건\n`)
for (const { rule, items } of byRule.values()) {
  console.error(`  [${rule.id}] ${rule.msg}`)
  for (const v of items.slice(0, 12)) {
    console.error(`    ${v.file}:${v.line}  ${v.found.join(' ')}`)
  }
  if (items.length > 12) console.error(`    ... 외 ${items.length - 12}건`)
  console.error('')
}
console.error('예외가 필요하면 해당 줄이나 윗줄에 `design-token-exempt: <이유>` 주석을 단다.\n')
process.exit(1)
