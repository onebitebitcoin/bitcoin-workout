import { describe, it, expect } from 'vitest'

// 프로필 화면 달력이 쓰는 실제 모듈을 그대로 검증한다.
// 예전에는 같은 함수를 이 파일에 복사해두고 그 복사본을 테스트해서,
// utils/calendar.ts 가 깨져도 이 테스트는 통과했다.
import { getDaysInMonth, getFirstDayIndex, pad2 } from '../utils/calendar'

describe('getDaysInMonth', () => {
  it('1월은 31일', () => expect(getDaysInMonth(2025, 1)).toBe(31))
  it('2월 평년은 28일', () => expect(getDaysInMonth(2025, 2)).toBe(28))
  it('2월 윤년은 29일', () => expect(getDaysInMonth(2024, 2)).toBe(29))
  it('4월은 30일', () => expect(getDaysInMonth(2025, 4)).toBe(30))
  it('12월은 31일', () => expect(getDaysInMonth(2025, 12)).toBe(31))
})

describe('getFirstDayIndex', () => {
  it('2025-01-01은 수요일 → index 2', () => expect(getFirstDayIndex(2025, 1)).toBe(2))
  it('2025-04-01은 화요일 → index 1', () => expect(getFirstDayIndex(2025, 4)).toBe(1))
  it('월요일(index 0) 계산이 올바르다', () => {
    // 2026-06-01은 월요일
    expect(getFirstDayIndex(2026, 6)).toBe(0)
  })
  it('일요일(index 6) 계산이 올바르다', () => {
    // 2025-06-01은 일요일
    expect(getFirstDayIndex(2025, 6)).toBe(6)
  })
})

describe('pad2', () => {
  it('한 자리 숫자를 두 자리로', () => expect(pad2(5)).toBe('05'))
  it('두 자리 숫자는 그대로', () => expect(pad2(12)).toBe('12'))
  it('0은 00으로', () => expect(pad2(0)).toBe('00'))
})
