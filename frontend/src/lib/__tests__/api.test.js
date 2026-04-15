import api from '../api'

describe('api module', () => {
  it('exports public signup function', () => {
    expect(typeof api.public.createSignup).toBe('function')
  })

  it('exports login function', () => {
    expect(typeof api.login).toBe('function')
  })

  it('does not export retired createSignup', () => {
    expect(api.createSignup).toBeUndefined()
  })

  it('does not export retired listMySignups', () => {
    expect(api.listMySignups).toBeUndefined()
  })

  it('does not export admin.overrides', () => {
    expect(api.admin.overrides).toBeUndefined()
  })
})
