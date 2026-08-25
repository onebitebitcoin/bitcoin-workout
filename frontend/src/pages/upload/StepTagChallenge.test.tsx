import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import StepTagChallenge from './StepTagChallenge'
import client from '../../api/client'

vi.mock('../../api/client', () => ({
  default: { get: vi.fn() },
}))

const mockedGet = vi.mocked(client.get)

function buildProps(overrides: Partial<React.ComponentProps<typeof StepTagChallenge>> = {}) {
  return {
    previewUrl: null,
    mainCategory: null,
    setMainCategory: vi.fn(),
    subCategory: null,
    setSubCategory: vi.fn(),
    subCategoryInput: '',
    setSubCategoryInput: vi.fn(),
    addSubCategoryFromInput: vi.fn(),
    hasChallenge: null,
    setHasChallenge: vi.fn(),
    selectedChallenge: null,
    selectedChallengeId: null,
    limitError: '',
    setLimitError: vi.fn(),
    clearChallenge: vi.fn(),
    onNext: vi.fn(),
    openChallengeModal: vi.fn(),
    showChallengeModal: false,
    setShowChallengeModal: vi.fn(),
    challengeSearch: '',
    setChallengeSearch: vi.fn(),
    displayedChallenges: [],
    selectChallenge: vi.fn(),
    ...overrides,
  }
}

describe('StepTagChallenge', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('renders the two required main categories', () => {
    render(<StepTagChallenge {...buildProps()} />)
    expect(screen.getByRole('button', { name: '가벼운 활동' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '땀 흘리는 운동' })).toBeInTheDocument()
  })

  it('selecting a main category calls setMainCategory', async () => {
    const setMainCategory = vi.fn()
    render(<StepTagChallenge {...buildProps({ setMainCategory })} />)
    await userEvent.click(screen.getByRole('button', { name: '땀 흘리는 운동' }))
    expect(setMainCategory).toHaveBeenCalledWith('땀 흘리는 운동')
  })

  it('does not show sub-category options before a main category is chosen', () => {
    render(<StepTagChallenge {...buildProps()} />)
    expect(screen.queryByText('세부 종류 (선택)')).not.toBeInTheDocument()
  })

  it('shows the matching sub-category options once a main category is chosen', () => {
    render(<StepTagChallenge {...buildProps({ mainCategory: '가벼운 활동' })} />)
    expect(screen.getByText('세부 종류 (선택)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '계단 오르기' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '산책' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '런닝' })).not.toBeInTheDocument()
  })

  it('shows sweaty-exercise sub-categories when that main category is chosen', () => {
    render(<StepTagChallenge {...buildProps({ mainCategory: '땀 흘리는 운동' })} />)
    expect(screen.getByRole('button', { name: '런닝' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '조깅' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '웨이트' })).toBeInTheDocument()
  })

  it('selecting a sub-category calls setSubCategory', async () => {
    const setSubCategory = vi.fn()
    render(<StepTagChallenge {...buildProps({ mainCategory: '땀 흘리는 운동', setSubCategory })} />)
    await userEvent.click(screen.getByRole('button', { name: '런닝' }))
    expect(setSubCategory).toHaveBeenCalledWith('런닝')
  })

  it('typing a custom sub-category and submitting calls addSubCategoryFromInput', async () => {
    const addSubCategoryFromInput = vi.fn()
    render(<StepTagChallenge {...buildProps({ mainCategory: '가벼운 활동', subCategoryInput: '필라테스', addSubCategoryFromInput })} />)
    await userEvent.click(screen.getByPlaceholderText('직접 입력 후 Enter'))
    await userEvent.keyboard('{Enter}')
    expect(addSubCategoryFromInput).toHaveBeenCalled()
  })

  it('shows the selected sub-category as a removable chip', async () => {
    const setSubCategory = vi.fn()
    render(<StepTagChallenge {...buildProps({ mainCategory: '가벼운 활동', subCategory: '산책', setSubCategory })} />)
    const chipRemoveButtons = screen.getAllByText('산책')
    expect(chipRemoveButtons.length).toBeGreaterThan(0)
    const chip = chipRemoveButtons[0].closest('div')
    const removeBtn = chip?.querySelector('button')
    expect(removeBtn).not.toBeNull()
    await userEvent.click(removeBtn as HTMLButtonElement)
    expect(setSubCategory).toHaveBeenCalledWith('산책')
  })

  it('blocks proceeding and shows an error when no main category is selected', async () => {
    const onNext = vi.fn()
    const setLimitError = vi.fn()
    render(<StepTagChallenge {...buildProps({ onNext, setLimitError })} />)
    await userEvent.click(screen.getByRole('button', { name: /다음/ }))
    expect(setLimitError).toHaveBeenCalledWith('카테고리를 선택해주세요.')
    expect(onNext).not.toHaveBeenCalled()
    expect(mockedGet).not.toHaveBeenCalled()
  })

  it('proceeds for light-activity category without calling the API', async () => {
    const onNext = vi.fn()
    render(<StepTagChallenge {...buildProps({ mainCategory: '가벼운 활동', onNext })} />)
    await userEvent.click(screen.getByRole('button', { name: /다음/ }))
    expect(mockedGet).not.toHaveBeenCalled()
    expect(onNext).toHaveBeenCalled()
  })

  it('proceeds for sweaty-exercise category without calling the API', async () => {
    const onNext = vi.fn()
    render(<StepTagChallenge {...buildProps({ mainCategory: '땀 흘리는 운동', onNext })} />)
    await userEvent.click(screen.getByRole('button', { name: /다음/ }))
    await waitFor(() => expect(onNext).toHaveBeenCalled())
    expect(mockedGet).not.toHaveBeenCalled()
  })
})
