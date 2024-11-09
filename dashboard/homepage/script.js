document.getElementById('waitlist-form').addEventListener('submit', function(event) {
    event.preventDefault(); // Prevent the default form submission

    const formData = new FormData(this); // Create a FormData object from the form
    const signup_form = this;

    // Convert FormData to JSON
    const formObject = {};
    formData.forEach((value, key) => {
        formObject[key] = value;
    });
    const jsonString = JSON.stringify(formObject);

    // Post the data to the API endpoint
    //fetch('http://localhost:8000/signup_waitlist', {
    fetch('https://app.supercog.ai/signup_waitlist', {
            method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: jsonString,
    })
    .then(response => {
        if (response.status !== 200) {
            throw new Error('Failed to fetch: Server responded with a status of ' + response.status);
        }
        return response.json();
    }).then(data => {
        console.log('Success:', data);
        signup_form.reset();
        alert('Thanks for signing up!');
    })
    .catch((error) => {
        console.error('Error:', error);
        alert('Sorry, there was an error submitting the form.');
    });
});
