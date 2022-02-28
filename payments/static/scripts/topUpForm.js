$(document).ready(function() {

    //zip code formatting
    $("#postal-code").keyup(function() {
        zipcode = $(this).val();
        zipcode = zipcode.replace(/-/g, '');      // remove all occurrences of '-'

        if(zipcode.length >= 5 ) {
            $(this).val(zipcode.substring(0, 2) + "-" + zipcode.substring(2, 5));
        }
    });

});