function onOpen() {
  var form = FormApp.getActiveForm();
  ScriptApp.newTrigger('onFormSubmit'). forForm(form).onFormSubmit().create();
}

var posted = false;

function onFormSubmit(e) {
  if (posted) return;
  posted = true;

  var data = {
    "form": {
      "id": e.source.getId(),
      "title": e.source.getTitle() ? e.source.getTitle() : "Untitled Form",
      "is_private": e.source.requiresLogin(),
      "is_published": e.source.isAcceptingResponses()
    },
    "response": {
      "id": e.response.getId(),
      "timestamp": e.response.getTimestamp(),
      "editUrl": e.response.getEditResponseUrl(),
      "payload": e.response.getItemResponses().map(function(y) {
        return {
          h: y.getItem().getTitle(),
          k: y.getResponse()
        }
      }, this).reduce(function(r, y) {
        r[y.h] = y.k;
        return r;
      }, {})
    }
  };

  var options = {
    method: "post",
    payload: JSON.stringify(data, null, 2),
    contentType: "application/json; charset=utf-8",
  };

  UrlFetchApp.fetch("https://rtc.ukump.com/patients/form/postback", options);
}
