import { assertEquals } from 'jsr:@std/assert@1.0.13'
import { sniffImageType } from './images.ts'

const bytes = (...b: number[]) => new Uint8Array(b)
const ascii = (s: string) => new TextEncoder().encode(s)

Deno.test('tells PNG, JPEG and WebP from their first bytes', () => {
  assertEquals(sniffImageType(bytes(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0)), 'image/png')
  assertEquals(sniffImageType(bytes(0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0, 0, 0, 0, 0)), 'image/jpeg')
  assertEquals(sniffImageType(ascii('RIFF\x10\x00\x00\x00WEBPVP8 ')), 'image/webp')
})

Deno.test('knows nothing else, whatever it is named', () => {
  assertEquals(sniffImageType(ascii('GIF89a......')), null)
  assertEquals(sniffImageType(ascii('<html><body>')), null)
  assertEquals(sniffImageType(ascii('RIFF....WAVE')), null)
  assertEquals(sniffImageType(bytes()), null)
})
