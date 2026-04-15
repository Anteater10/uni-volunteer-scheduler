export function cn(...args) {
  return args.flat(Infinity).filter(Boolean).join(' ')
}
export default cn
