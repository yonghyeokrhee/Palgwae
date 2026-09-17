#!/usr/bin/env node
// The same Python wheel backs every client. Nothing runs at package installation.
import { spawn } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
let wheels;
try {
  wheels = readdirSync(join(root, 'vendor')).filter(name => name.endsWith('.whl'));
} catch {
  wheels = [];
}
if (wheels.length !== 1) {
  process.stderr.write('Palgwae: package must contain exactly one runtime wheel. Use an official release archive.\n');
  process.exit(2);
}
const child = spawn('uv', ['tool', 'run', '--from', join(root, 'vendor', wheels[0]),
  'palgwae', ...process.argv.slice(2)], { stdio: 'inherit', shell: false });
child.on('error', error => {
  process.stderr.write(error.code === 'ENOENT'
    ? 'Palgwae requires uv. Install it from https://docs.astral.sh/uv/getting-started/installation/ and retry.\n'
    : `Palgwae could not start uv (${error.code}).\n`);
  process.exitCode = 2;
});
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}
child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal === 'SIGINT' ? 130 : 143);
});
