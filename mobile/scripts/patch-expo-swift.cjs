const fs = require('node:fs');
const path = require('node:path');

// Swift can crash lowering this cast pattern on a consuming, noncopyable Result.
// Exception already conforms to Error, so the cast is unnecessary.
// https://github.com/swiftlang/swift/issues/93625
const root = path.dirname(require.resolve('expo-modules-core/package.json'));
const file = path.join(root, 'ios/Core/Functions/AsyncFunctionDefinition.swift');
const source = fs.readFileSync(file, 'utf8');
const before = 'case .failure(let error as any Error):';
if (source.includes(before)) {
  fs.writeFileSync(file, source.replace(before, 'case .failure(let error):'));
  console.log('Applied Expo Swift compiler workaround.');
}
