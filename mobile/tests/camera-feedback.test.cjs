const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/camera-feedback.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const moduleExports = {};
vm.runInNewContext(source, { exports: moduleExports });
const feedback = moduleExports.cameraFeedback;
const historical = moduleExports.isHistoricalQuestion;

test('historical questions do not request a fresh camera view', () => {
  for (const question of [
    'What did I pass earlier?',
    'What did I see before entering the room?',
    'What did I see before lunch?',
    'Where was my backpack five minutes ago?',
    'Qu’ai-je vu avant le déjeuner ?',
    'What was on the sign five minutes ago?',
    'Did I see a backpack in the last fifteen minutes?',
    'Qu’ai-je vu il y a cinq minutes ?',
    'ماذا رأيت قبل خمس دقائق؟',
    'شو شفت من خمس دقايق؟',
    'What did I see around 2:30 PM?',
    'What did I see at 2:30 PM?',
    'Qu’ai-je vu vers 14 h 30 ?',
    'ماذا رأيت حوالي الساعة ٢:٣٠ مساءً؟',
  ]) assert.equal(historical(question), true);
  assert.equal(historical('What is in front of me?'), false);
});

test('spatial questions remain current-view questions', () => {
  for (const question of [
    "What's around me?",
    'What is around the corner?',
    'What about that chair?',
    'What is between the door and the chair?',
    'Is there an obstacle before me?',
    'What is before the stairs?',
    'Is there a curb before the road?',
    'Qu’y a-t-il avant l’escalier ?',
    'شو في قبل الدرج؟',
    'What is between 2 doors and 3 chairs?',
    'About how far is the door?',
    'Qu’y a-t-il vers la porte ?',
    'Qu’y a-t-il entre la porte et la chaise ?',
    'Est-ce qu’il y a une chaise ?',
    'ماذا يوجد حوالي الباب؟',
    'ماذا يوجد بين الباب والكرسي؟',
    'ماذا يوجد ضمن خمس دقايق؟',
  ]) assert.equal(historical(question), false, question);
});

test('camera advice names a view problem only when the answer supports it', () => {
  assert.match(feedback(true, "The ground isn't visible in this view."), /tilt the camera slightly downward/);
  assert.match(feedback(true, 'The image is too dark to identify the sign.'), /better light/);
  assert.match(feedback(true, 'The object is blurry.'), /hold the camera steady/i);
  assert.match(feedback(true, 'The object is cut off.'), /center it in the frame/);
});

test('recapture advice follows the answer language', () => {
  assert.match(feedback(true, 'Le sol n’est pas visible.', [], true, 'fr'), /Inclinez légèrement/);
  assert.match(feedback(true, 'L’image est floue.', [], true, 'fr'), /Tenez la caméra immobile/);
  assert.match(feedback(true, 'الصورة مظلمة.', [], true, 'ar'), /إضاءة أفضل/);
  assert.match(feedback(true, 'جزء من الهدف خارج الإطار.', [], true, 'ar'), /وسط الإطار/);
  assert.match(feedback(true, 'I cannot identify it confidently.', [], true, 'fr'), /centrez ce que vous voulez identifier/);
});

test('uncertainty alone receives neutral guidance and certain answers receive none', () => {
  const generic = feedback(true, 'I cannot identify it confidently.', ['quality_override']);
  assert.match(generic, /center what you want to identify/);
  assert.doesNotMatch(generic, /is too dark|ground isn't visible/);
  assert.equal(feedback(false, 'The ground is clearly visible.'), null);
  assert.equal(feedback(true, 'No nearby place found.', [], false), null);
  assert.match(feedback(true, 'I could not get a fresh frame.', ['current_view_timeout']), /fresh view/);
});
