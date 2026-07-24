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

  it('아이템이 없으면 효과 옵션이 보이지 않는다', () => {
    render(<StepMedia {...buildProps()} />)
    expect(screen.queryAllByRole('radio')).toHaveLength(0)
  })

  it('아이템이 있으면 효과 옵션 5개(없음/카툰/운동열/카툰+운동열/발자국)가 보인다', () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3 })} />)
    expect(screen.getAllByRole('radio')).toHaveLength(5)
  })

  it.each([
    ['카툰 필터', 'cartoon'],
    ['운동열 강조', 'heat'],
    ['카툰 + 운동열', 'cartoon_heat'],
    ['발자국', 'footsteps'],
  ])('%s 선택 시 setVideoFilter(%s) 호출', async (label, value) => {
    const setVideoFilter = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, setVideoFilter })} />)
    await userEvent.click(screen.getByRole('radio', { name: label }))
    expect(setVideoFilter).toHaveBeenCalledWith(value)
  })

  it('효과 없음 선택 시 setVideoFilter(빈 값) 호출', async () => {
    const setVideoFilter = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, videoFilter: 'cartoon', setVideoFilter })} />)
    await userEvent.click(screen.getByRole('radio', { name: '효과 없음' }))
    expect(setVideoFilter).toHaveBeenCalledWith('')
  })

  it('선택된 옵션은 aria-checked=true', () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, videoFilter: 'footsteps' })} />)
    expect(screen.getByRole('radio', { name: '발자국' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: '카툰 필터' })).toHaveAttribute('aria-checked', 'false')
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
