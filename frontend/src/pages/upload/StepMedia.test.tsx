import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import StepMedia, { type MediaItem } from './StepMedia'

vi.mock('../../api/client', () => ({
  default: { post: vi.fn(() => new Promise(() => undefined)) },
}))
import client from '../../api/client'

function makeItem(kind: 'video' | 'image', id: string, durationSec?: number): MediaItem {
  return {
    id,
    kind,
    file: new File(['x'], `${id}.${kind === 'video' ? 'mp4' : 'png'}`, { type: kind === 'video' ? 'video/mp4' : 'image/png' }),
    previewUrl: `blob:${id}`,
    durationSec,
  }
}

function buildProps(overrides: Partial<React.ComponentProps<typeof StepMedia>> = {}) {
  return {
    fileInputRef: { current: null },
    items: [] as MediaItem[],
    onAddFiles: vi.fn(),
    onRemove: vi.fn(),
    onReorder: vi.fn(),
    estimatedSeconds: 0,
    error: '',
    onNext: vi.fn(),
    videoFilter: '' as const,
    setVideoFilter: vi.fn(),
    ...overrides,
  }
}

describe('StepMedia', () => {
  it('아이템이 없으면 다음 버튼이 비활성', () => {
    render(<StepMedia {...buildProps()} />)
    expect(screen.getByRole('button', { name: '다음' })).toBeDisabled()
  })

  it('아이템을 렌더한다', () => {
    const items = [makeItem('image', 'a'), makeItem('video', 'b', 5)]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 8 })} />)
    expect(screen.getAllByLabelText('remove')).toHaveLength(2)
  })

  it('예상 길이가 60초를 초과하면 다음 버튼 비활성', () => {
    const items = [makeItem('video', 'b', 65)]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 65 })} />)
    expect(screen.getByRole('button', { name: '다음' })).toBeDisabled()
  })

  it('정상 구성이면 다음 클릭 시 onNext 호출', async () => {
    const onNext = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, onNext })} />)
    await userEvent.click(screen.getByRole('button', { name: '다음' }))
    expect(onNext).toHaveBeenCalledOnce()
  })

  it('삭제 버튼 클릭 시 onRemove(id) 호출', async () => {
    const onRemove = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, onRemove })} />)
    await userEvent.click(screen.getByLabelText('remove'))
    expect(onRemove).toHaveBeenCalledWith('a')
  })

  it('아이템이 없으면 효과 드롭다운이 보이지 않는다', () => {
    render(<StepMedia {...buildProps()} />)
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(screen.queryByLabelText('영상 효과')).toBeNull()
  })

  it('닫힌 상태에선 선택된 효과만 버튼에 보이고 옵션 목록은 감춰진다', () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, videoFilter: 'heat' })} />)
    expect(screen.getByRole('button', { name: '영상 효과' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('드롭다운을 열면 효과 옵션 5개가 보인다', async () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3 })} />)
    await userEvent.click(screen.getByRole('button', { name: '영상 효과' }))
    expect(screen.getAllByRole('option')).toHaveLength(5)
  })

  it.each([
    ['카툰 필터', 'cartoon'],
    ['해시열', 'heat'],
    ['카툰 + 해시열', 'cartoon_heat'],
    ['발자국', 'footsteps'],
  ])('%s 옵션 선택 시 setVideoFilter(%s) 호출', async (label, value) => {
    const setVideoFilter = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, setVideoFilter })} />)
    await userEvent.click(screen.getByRole('button', { name: '영상 효과' }))
    await userEvent.click(screen.getByRole('option', { name: label }))
    expect(setVideoFilter).toHaveBeenCalledWith(value)
  })

  it('효과 없음 옵션 선택 시 setVideoFilter(빈 값) 호출', async () => {
    const setVideoFilter = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, videoFilter: 'cartoon', setVideoFilter })} />)
    await userEvent.click(screen.getByRole('button', { name: '영상 효과' }))
    await userEvent.click(screen.getByRole('option', { name: '효과 없음' }))
    expect(setVideoFilter).toHaveBeenCalledWith('')
  })

  it('선택된 옵션은 열었을 때 aria-selected=true', async () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, videoFilter: 'footsteps' })} />)
    await userEvent.click(screen.getByRole('button', { name: '영상 효과' }))
    expect(screen.getByRole('option', { name: '발자국' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('option', { name: '카툰 필터' })).toHaveAttribute('aria-selected', 'false')
  })

  it.each(['cartoon', 'heat', 'footsteps'] as const)(
    '%s 선택이면 filter-preview 요청을 보낸다', async (videoFilter) => {
      const items = [makeItem('image', 'a')]
      render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, videoFilter })} />)
      await waitFor(() =>
        expect(vi.mocked(client.post)).toHaveBeenCalledWith(
          '/videos/filter-preview',
          expect.any(FormData),
          expect.objectContaining({ responseType: 'blob' }),
        ),
      )
    },
  )
})
