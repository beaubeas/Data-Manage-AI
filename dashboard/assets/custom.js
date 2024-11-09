function scrollChat(delay) {
    const chatout = document.getElementById('chatoutput');
    if (chatout) {
        chatout.scrollTop = chatout.scrollHeight;
    }
    window._override_autoscroll = false;
}
window._override_autoscroll = false;

window.renableAutoscroll = function() {
    console.log("SOMEONE CALLED RENABLE AUTOSCROLL");
    window._override_autoscroll = false;
}

window.setupChatScrolling = function() {
    console.log("SETTING UP CHAT SCROLLING");
    window._override_autoscroll = false;
    const chatoutput = document.getElementById('chatoutput');
    const chatwindow = document.getElementById('chatwindow');
       
    if (chatwindow) {
        let lastScrollHeight = chatwindow.scrollHeight;
        const mutationObserver = new MutationObserver(() => {
            if (!window._override_autoscroll && chatwindow.scrollHeight > lastScrollHeight) {
                console.log("Chatout div changed size, calling scrollChat");
                lastScrollHeight = chatwindow.scrollHeight;
                window.scrollChat();
            }
        });

        // Start observing the scrollable div
        mutationObserver.observe(chatwindow, { childList: true, subtree: true });

        // let user override auto-scroll 
        window.addEventListener("wheel", (event) => {
            if (event.deltaY < -5 && !window._override_autoscroll) {
                //console.log("override autoscroll");
                window._override_autoscroll = true;
            }
        });

        // and let them resume by scolling the chat to the bottom
        chatoutput.addEventListener("scroll", (event) => {
            if ((chatoutput.scrollTop + chatoutput.offsetHeight) > (chatoutput.scrollHeight-250)) {
                //console.log("renable autoscroll");
                window._override_autoscroll = false;
            }
        });

        setTimeout(window.scrollChat, 1500);
    }
}

if (document.getElementById('chatoutput')) {
    window.setupChatScrolling();
} else {
    setTimeout(window.setupChatScrolling, 2000);
}

Array.prototype.forEach.call(document.getElementsByTagName('input'), function(elt) {
    elt.autocomplete = 'off';
});

// Ajax POST from Oauth login buttons

window.setup_oauth_form = function(engine_host) {
    console.log("Setting up oauth form: ", engine_host);
    var form = document.getElementById("oauth_form");
    async function handleSubmit(event) {
        console.log("Submitting oauth form")
        event.preventDefault();
        var data = new FormData(event.target);
        console.log(data);
        var submitdata = {"options":{}};
        try {
            submitdata['options']['customhost'] = 
                document.getElementById('cred_form')['options:custom_host'].value;
        } catch (e) {} 
        data.forEach(function(value, key){
            if (key.startsWith("options")) {
                submitdata["options"][key.split(":")[1]] = value;
            } else {
                submitdata[key] = value;
            }
            submitdata[key] = value;
        });
        submitdata['cred_name'] = document.getElementById('cred_name_input').value;
        submitdata['return_url'] = submitdata['return_url'] + "?cred_name=" + submitdata['cred_name'];
        // event.target.action
        server_host = engine_host;
        if (!server_host) {
            alert("Error server host not set");
            return;
        }
        fetch(server_host + "/run_oauth", {
            method: 'POST',
            body: JSON.stringify(submitdata),
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            }).then(response => {
                response.json().then(data => {
                    var newloc = server_host + data.headers['Location'];
                    window.location = newloc;
                });
            }).catch(error => {
                console.error("Error:", error);
            });
    }
    if (form) {
        form.addEventListener("submit", handleSubmit);
    }
}

// global
STORAGE_KEY_DEFAULT = 'supercog_history';
STORAGE_KEY = STORAGE_KEY_DEFAULT;

function submitOnEnter(event) {
    var textfield = document.getElementById("question");
    if (event.which === 13 && !event.shiftKey) {
        if (!event.repeat) {
            document.getElementById("submit_button").click();
        }

        event.preventDefault(); // Prevents the addition of a new line in the text field
    } else if (event.key === "ArrowUp" && !event.shiftKey) {
        // Check if cursor is at the beginning of the text field
        if (textfield.selectionStart === 0) {
            if (input_position >= 0) {
                textfield.value = input_history[input_position];
                var sel = textfield.value.length;
                setTimeout(function() {
                    textfield.selectionStart = sel;
                    textfield.selectionEnd = sel;
                }, 0);
                input_position--;
            }
        }
    } else if (event.key === "ArrowDown" && !event.shiftKey) {
        if (input_position < input_history.length-1) {
            input_position++;
            textfield.value = input_history[input_position];
            textfield.selectionStart = 1000;
        } else {
            textfield.value = "";
        }
    }   
}

var input_history = null;
var input_position = -1;

function recordInput() {
    if (input_history) {
        input_history.push(document.getElementById("question").value);
        // keep history size manageable
        if (input_history.length > 100) {
            input_history.shift();
        }
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(input_history));
        input_position = input_history.length-1;
    }
}

function setupPromptHistoryOnFocus() {
    var textfield = document.getElementById("question");
    textfield.removeEventListener("keydown", submitOnEnter);
    textfield.removeEventListener("keydown", submitOnEnter);
    textfield.addEventListener("keydown", submitOnEnter);

    // Whenever our prompt field gets focus, we will setup the command
    // history. We can't use page load because Reflex is SPA and only
    // loads the page once. So every focus we figure out if the
    // active agent has changed, and if so then we swap the history.
    pathmatch = window.location.pathname.match(/[a-z\d]+(-[a-z\d]+)+/);

    if (pathmatch) {
        new_key = pathmatch[0] + '_history';
        STORAGE_KEY = new_key;
    }

    //console.log("Retriveing prompt history for key: ", STORAGE_KEY);
    input_history = window.localStorage.getItem(STORAGE_KEY);
    if (!input_history) {
        input_history = [];
        input_position = -1;
    } else {
        input_history = JSON.parse(input_history);
        input_position = input_history.length-1;
    }

    document.getElementById("submit_button").removeEventListener("click", recordInput);
    document.getElementById("submit_button").addEventListener("click", recordInput);       
}

textfield = document.getElementById("question");
if (textfield) {
    textfield.removeEventListener("focus", setupPromptHistoryOnFocus);
    textfield.addEventListener("focus", setupPromptHistoryOnFocus);
}

function setupCancelButton() {
    var cancelButton = document.getElementById("cancel_button");
    if( cancelButton) {
        console.log("cancel button found");
        // Define what happens when the button is clicked
        cancelButton.onclick = function() {
            var cancelurl = this.getAttribute('data-cancel');
            fetch(cancelurl);
        }
    } else {
        console.log("no cancel button");
    }
}
//window.addEventListener("load", setupCancelButton);
window._setupCancelButton = setupCancelButton;


// UNUSED
function setupEditorPane() {
    function toggleEditorPane() {
        const startFlex = 20;
        const endFlex = 0;
        const duration = 2000; // adjust this value as needed
        let currentFlex = startFlex;
    
        let elem = document.getElementById('editor_pane');
        if (elem) {
            function updateStyle() {
            elem.style.flex = currentFlex;
            if (currentFlex > endFlex) {
                currentFlex -= (startFlex - endFlex) / (duration / 1000);
                requestAnimationFrame(updateStyle);
            } else {
                elem.style.display = 'none';
            }
            }
        
            updateStyle();  
        } else {
            console.error("Could not find editor_pane");
        }
    }

    let toggle = document.getElementById('toggle_button');
    if (toggle) {
        toggle.onclick = function() {
        toggleEditorPane();
        }
    } else {
        console.error("Could not find toggle_button");
    }
}

function openPopup(url, title) {
    w = 600;
    h = 500;
    // Calculate the position to center the popup
    const left = (screen.width / 2) - (w / 2);
    const top = (screen.height / 2) - (h / 2);
  
    // Open the popup window
    return window.open(url, title, `width=${w},height=${h},top=${top},left=${left}`);
  }
window.openPopup = openPopup;

window.copy_code_to_clipboard = function(event) {
    var node = event.target;
    while (node != undefined && node.nodeName != "DIV") {
        node = node.parentNode;
    }
    if (node) {
        console.log(node);
        var code = node.innerText;
        code = code.trim();
        console.log(code);
        navigator.clipboard.writeText(code);
    }
}

window.grabPromptFocus = function() {
    var textfield = document.getElementById("question");
    if (textfield) {
        textfield.focus();
    }
}

window.setupCopyButtons = function() {
    //console.log("Setting up copy buttons");
    var copyButtons = document.getElementsByClassName("copy_button");
    for (var i = 0; i < copyButtons.length; i++) {
        copyButtons[i].addEventListener("click", copy_code_to_clipboard);
        copyButtons[i].addEventListener("click", copy_code_to_clipboard);
    }
}
setInterval(window.setupCopyButtons, 1000);
