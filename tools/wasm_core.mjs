// Trusted private DTO ABI. Used only by private Core equivalence tests; no browser client.
export class WasmCore {
  constructor(instance) { this.exports = instance.exports; }
  call(request) {
    const e = this.exports, raw = new TextEncoder().encode(JSON.stringify(request));
    const address = e.tankbot_input(raw.length);
    if (!address) throw Error("Private DTO exceeds WASM limit");
    new Uint8Array(e.memory.buffer, address, raw.length).set(raw);
    const length = e.tankbot_exchange(), pointer = e.tankbot_output();
    return new TextDecoder("utf-8", {fatal:true}).decode(new Uint8Array(e.memory.buffer, pointer, length));
  }
}
