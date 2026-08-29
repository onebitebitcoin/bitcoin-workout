import { describe, it, expect, beforeEach } from 'vitest'
import { useThemeStore, THEMES, THEME_LABELS, initTheme } from '../store/theme'

// tokens.css에서 삭제된 구 테마 이름. 삭제 전에는 유효했으므로 사용자 localStorage(app-theme)에
// 여전히 남아있을 수 있다 — initTheme이 이런 값을 안전하게 기본값으로 되돌리는지 검증한다.
const REMOVED_THEMES = ['volt-light', 'arctic', 'forest']

beforeEach(() => {
  useThemeStore.setState({ theme: 'bitcoin' })
  document.documentElement.removeAttribute('data-theme')
})

describe('useThemeStore', () => {
  it('기본 테마는 bitcoin', () => {
    expect(useThemeStore.getState().theme).toBe('bitcoin')
  })

  it('setTheme으로 테마를 변경한다', () => {
    useThemeStore.getState().setTheme('sapphire')
    expect(useThemeStore.getState().theme).toBe('sapphire')
  })

  it('setTheme은 data-theme 속성을 설정한다', () => {
    useThemeStore.getState().setTheme('indigo')
    expect(document.documentElement.getAttribute('data-theme')).toBe('indigo')
  })

  it('모든 테마를 순환할 수 있다', () => {
    for (const t of THEMES) {
      useThemeStore.getState().setTheme(t)
      expect(useThemeStore.getState().theme).toBe(t)
    }
  })
})

describe('THEMES / THEME_LABELS', () => {
  it('THEMES에 volt가 포함된다', () => {
    expect(THEMES).toContain('volt')
  })

  it('모든 테마에 레이블이 존재한다', () => {
    for (const t of THEMES) {
      expect(THEME_LABELS[t]).toBeTruthy()
    }
  })
})

describe('initTheme', () => {
  it('override 없으면 저장된 테마 적용', () => {
    useThemeStore.setState({ theme: 'indigo' })
    initTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('indigo')
  })

  it('유효한 override는 적용된다', () => {
    initTheme('sapphire')
    expect(document.documentElement.getAttribute('data-theme')).toBe('sapphire')
  })

  it.each(THEMES)('현재 살아있는 테마 %s는 override로 적용된다', (t) => {
    initTheme(t)
    expect(document.documentElement.getAttribute('data-theme')).toBe(t)
    expect(useThemeStore.getState().theme).toBe(t)
  })

  it.each(REMOVED_THEMES)(
    '저장된 테마가 삭제된 구 테마 이름(%s)이면 기본값 bitcoin으로 마이그레이션',
    (removed) => {
      useThemeStore.setState({ theme: removed as never })
      initTheme()
      expect(document.documentElement.getAttribute('data-theme')).toBe('bitcoin')
      expect(useThemeStore.getState().theme).toBe('bitcoin')
    },
  )

  it('override가 삭제된 구 테마 이름이어도 저장된 유효한 테마를 그대로 사용한다', () => {
    useThemeStore.setState({ theme: 'sapphire' })
    initTheme('volt-light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('sapphire')
  })

  it('저장된 테마와 override가 모두 삭제된 구 테마 이름이면 기본값 bitcoin으로 마이그레이션', () => {
    useThemeStore.setState({ theme: 'volt-light' as never })
    initTheme('arctic')
    expect(document.documentElement.getAttribute('data-theme')).toBe('bitcoin')
    expect(useThemeStore.getState().theme).toBe('bitcoin')
  })

  it('한 번도 존재한 적 없는 override는 무시하고 저장된 테마 사용', () => {
    useThemeStore.setState({ theme: 'volt' })
    initTheme('invalid-theme')
    expect(document.documentElement.getAttribute('data-theme')).toBe('volt')
  })

  it('null override는 저장된 테마 사용', () => {
    useThemeStore.setState({ theme: 'sapphire' })
    initTheme(null)
    expect(document.documentElement.getAttribute('data-theme')).toBe('sapphire')
  })
})
