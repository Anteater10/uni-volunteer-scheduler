import api from '../api'

describe('api module', () => {
  it('exports createSignup as a function', () => {
    expect(typeof api.createSignup).toBe('function')
  })
})
