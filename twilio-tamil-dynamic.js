// twilio-tamil-dynamic.js
exports.handler = function(context, event, callback) {
  const name = event.name || '';
  const dosage = event.dosage || '';
  const time = event.time || '';
  const twiml = `
<Response>
  <Say language="ta-IN" voice="Polly.Kajal">
    உங்கள் மருந்து ${name} ${dosage} எடுத்துக்கொள்ளும் நேரம் ${time} ஆகிவிட்டது. தயவு செய்து மருந்தை எடுத்துக்கொள்ளுங்கள் நன்றி.
  </Say>
</Response>`;
  callback(null, twiml);
};