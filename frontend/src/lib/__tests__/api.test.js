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

  it('exposes api.admin.users.invite / deactivate / reactivate', () => {
    expect(typeof api.admin.users.invite).toBe('function')
    expect(typeof api.admin.users.deactivate).toBe('function')
    expect(typeof api.admin.users.reactivate).toBe('function')
  })

  it('exposes attendance + no-show CSV helpers', () => {
    expect(typeof api.admin.analytics.attendanceRatesCsv).toBe('function')
    expect(typeof api.admin.analytics.noShowRatesCsv).toBe('function')
  })

  it('still does NOT expose api.admin.overrides (guard)', () => {
    expect(api.admin.overrides).toBeUndefined()
  })
})
