import { describe, it, expect } from 'vitest'

// ko/en 로케일 JSON을 정적으로 전부 로드한다.
// 새 네임스페이스(JSON 파일)가 추가되면 하드코딩 없이 자동으로 포함된다.
const koModules = import.meta.glob('../i18n/locales/ko/*.json', { eager: true }) as Record<
  string,
  { default: unknown }
>
const enModules = import.meta.glob('../i18n/locales/en/*.json', { eager: true }) as Record<
  string,
  { default: unknown }
>

function namespaceFromPath(path: string): string {
  const match = path.match(/([^/]+)\.json$/)
  if (!match) throw new Error(`네임스페이스 파일명을 파싱할 수 없습니다: ${path}`)
  return match[1]
}

// 네임스페이스 목록은 locales/ko 디렉토리에서 동적으로 읽는다 (하드코딩 금지).
const namespaces = Object.keys(koModules).map(namespaceFromPath).sort()

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }

/**
 * 중첩 객체/배열을 "a.b.c" 형태의 점 표기 경로로 평탄화한다.
 * 배열도 인덱스를 경로 세그먼트로 취급해 키 정합성 검사에 포함시킨다.
 */
function flatten(value: JsonValue, prefix: string, out: Record<string, string>): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => flatten(item, prefix ? `${prefix}.${index}` : String(index), out))
    return
  }
  if (value !== null && typeof value === 'object') {
    for (const key of Object.keys(value)) {
      flatten(value[key], prefix ? `${prefix}.${key}` : key, out)
    }
    return
  }
  // leaf: 프로젝트 내 모든 i18n 리소스 값은 문자열이어야 한다.
  out[prefix] = String(value)
}

function loadFlatNamespace(
  modules: Record<string, { default: unknown }>,
  ns: string,
  lang: 'ko' | 'en',
): Record<string, string> {
  const entry = Object.entries(modules).find(([path]) => namespaceFromPath(path) === ns)
  if (!entry) {
    throw new Error(`[${lang}] "${ns}" 네임스페이스 JSON 파일을 찾을 수 없습니다.`)
  }
  const flat: Record<string, string> = {}
  flatten(entry[1].default as JsonValue, '', flat)
  return flat
}

const INTERPOLATION_RE = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g

function interpolationVars(value: string): Set<string> {
  const vars = new Set<string>()
  let match: RegExpExecArray | null
  INTERPOLATION_RE.lastIndex = 0
  while ((match = INTERPOLATION_RE.exec(value)) !== null) {
    vars.add(match[1])
  }
  return vars
}

describe('i18n ko/en 키 정합성 회귀 테스트', () => {
  it('네임스페이스 목록을 최소 1개 이상 자동으로 찾는다', () => {
    expect(namespaces.length).toBeGreaterThan(0)
  })

  describe.each(namespaces)('네임스페이스: %s', (ns) => {
    const koFlat = loadFlatNamespace(koModules, ns, 'ko')
    const enFlat = loadFlatNamespace(enModules, ns, 'en')

    it('ko와 en의 키 집합이 완전히 일치한다', () => {
      const koKeys = new Set(Object.keys(koFlat))
      const enKeys = new Set(Object.keys(enFlat))

      const onlyInKo = [...koKeys].filter((key) => !enKeys.has(key)).sort()
      const onlyInEn = [...enKeys].filter((key) => !koKeys.has(key)).sort()

      const messages: string[] = []
      if (onlyInKo.length > 0) {
        messages.push(`ko에만 있는 키 (en에서 누락): ${onlyInKo.map((k) => `${ns}.${k}`).join(', ')}`)
      }
      if (onlyInEn.length > 0) {
        messages.push(`en에만 있는 키 (ko에서 누락): ${onlyInEn.map((k) => `${ns}.${k}`).join(', ')}`)
      }

      expect(messages.join('\n'), messages.join('\n')).toBe('')
    })

    it('빈 문자열이나 공백만 있는 값이 없다', () => {
      const blankKo = Object.entries(koFlat)
        .filter(([, value]) => value.trim() === '')
        .map(([key]) => `ko:${ns}.${key}`)
      const blankEn = Object.entries(enFlat)
        .filter(([, value]) => value.trim() === '')
        .map(([key]) => `en:${ns}.${key}`)

      const blanks = [...blankKo, ...blankEn]
      expect(blanks.join(', '), `빈 값이 있는 키: ${blanks.join(', ')}`).toBe('')
    })

    it('보간 변수({{var}}) 집합이 ko/en에서 서로 같다', () => {
      const sharedKeys = Object.keys(koFlat).filter((key) => key in enFlat)
      const mismatches: string[] = []

      for (const key of sharedKeys) {
        const koVars = interpolationVars(koFlat[key])
        const enVars = interpolationVars(enFlat[key])

        const onlyKo = [...koVars].filter((v) => !enVars.has(v)).sort()
        const onlyEn = [...enVars].filter((v) => !koVars.has(v)).sort()

        if (onlyKo.length > 0 || onlyEn.length > 0) {
          const parts: string[] = []
          if (onlyKo.length > 0) parts.push(`ko에만 있는 변수 {{${onlyKo.join(', ')}}}`)
          if (onlyEn.length > 0) parts.push(`en에만 있는 변수 {{${onlyEn.join(', ')}}}`)
          mismatches.push(`${ns}.${key}: ${parts.join(', ')}`)
        }
      }

      expect(mismatches.join('\n'), mismatches.join('\n')).toBe('')
    })
  })
})
