#!/usr/bin/env node
const { spawn } = require('child_process');
const args = ['--from', 'flight-planner-mcp', 'flight-planner-mcp', ...process.argv.slice(2)];
const child = spawn('uvx', args, { stdio: 'inherit' });
child.on('error', (err) => { console.error('Failed to start uvx:', err.message); process.exit(1); });
child.on('exit', (code) => process.exit(code || 0));
