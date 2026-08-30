import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, afterEach, vi } from 'vitest'
import ExpandableCaption from '../components/ExpandableCaption'

/**
 * jsdom 은 레이아웃을 계산하지 않아 scrollHeight/clientHeight 가 항상 0이다.
 * 잘림 감지는 이 두 값의 비교로 이뤄지므로 프로토타입 getter 를 갈아끼워
 * "잘린 상태"와 "안 잘린 상태"를 직접 주입한다.
 */
function mockLayout(scrollHeight: number, clientHeight: number) {
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
    configurable: true,
    get: () => scrollHeight,
  })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get: () => clientHeight,
  })
}

afterEach(() => {
  Reflect.deleteProperty(HTMLElement.prototype, 'scrollHeight')
  Reflect.deleteProperty(HTMLElement.prototype, 'clientHeight')
})

describe('ExpandableCaption', () => {
  it('내용이 2줄 안에 들어가면 더보기 버튼이 없다', () => {
    mockLayout(40, 40)
    render(<ExpandableCaption text="짧은 설명" />)
    expect(screen.queryByRole('button', { name: /더보기/ })).toBeNull()
    expect(screen.getByText('짧은 설명')).toBeInTheDocument()
  })

  it('내용이 잘리면 더보기 버튼이 나온다', () => {
    mockLayout(200, 40)
    render(<ExpandableCaption text={'가'.repeat(500)} />)
    expect(screen.getByRole('button', { name: /더보기/ })).toBeInTheDocument()
  })

  it('더보기를 누르면 전문이 펼쳐지고 접기로 바뀐다', () => {
    mockLayout(200, 40)
    render(<ExpandableCaption text={'가'.repeat(500)} />)

    const more = screen.getByRole('button', { name: /더보기/ })
    expect(more).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(more)

    const less = screen.getByRole('button', { name: /접기/ })
    expect(less).toHaveAttribute('aria-expanded', 'true')
    expect(screen.queryByRole('button', { name: /더보기/ })).toBeNull()

    // 접기를 누르면 원래대로 돌아온다
    fireEvent.click(less)
    expect(screen.getByRole('button', { name: /더보기/ })).toBeInTheDocument()
  })

  it('펼치면 line-clamp 가 풀린다', () => {
    mockLayout(200, 40)
    const { container } = render(<ExpandableCaption text={'가'.repeat(500)} />)
    const paragraph = container.querySelector('p')!
    expect(paragraph.className).toContain('line-clamp-2')

    fireEvent.click(screen.getByRole('button', { name: /더보기/ }))
    expect(container.querySelector('p')!.className).not.toContain('line-clamp-2')
  })

  it('토글 클릭이 상위로 전파되지 않는다 (영상 재생/일시정지 방지)', () => {
    mockLayout(200, 40)
    const onParentClick = vi.fn()
    render(
      <div onClick={onParentClick}>
        <ExpandableCaption text={'가'.repeat(500)} />
      </div>,
    )
    fireEvent.click(screen.getByRole('button', { name: /더보기/ }))
    expect(onParentClick).not.toHaveBeenCalled()
  })

  it('본문이 바뀌면 펼침 상태가 초기화된다 (피드 카드 재사용 대비)', () => {
    mockLayout(200, 40)
    const { rerender } = render(<ExpandableCaption text={'가'.repeat(500)} />)
    fireEvent.click(screen.getByRole('button', { name: /더보기/ }))
    expect(screen.getByRole('button', { name: /접기/ })).toBeInTheDocument()

    rerender(<ExpandableCaption text={'나'.repeat(500)} />)
    expect(screen.getByRole('button', { name: /더보기/ })).toBeInTheDocument()
  })
})
