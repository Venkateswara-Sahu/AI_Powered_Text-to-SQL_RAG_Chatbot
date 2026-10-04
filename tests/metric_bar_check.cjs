// Evaluate the existing card's pure renderer without starting the app or API.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync('static/js/app.js', 'utf8');
const start = source.indexOf('const makeBar = ');
const end = source.indexOf('\n        };', start) + '\n        };'.length;
assert.ok(start >= 0 && end > start, 'Metric renderer must be available');
const render = new Function(source.slice(start, end) + '\nreturn makeBar;')();
const unavailable = render('Result-value coverage', null);
assert.match(unavailable, /Not measured/);
assert.doesNotMatch(unavailable, /NaN|width: 0%/);
assert.match(render('Result-value coverage', 0), /0\.00/);
assert.match(render('Result-value coverage', 0.5), /width: 50%/);
console.log('Metric renderer handles null, zero and finite scores.');
