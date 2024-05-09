frappe.listview_settings['Employee Checkin'] = {
	
	onload:function(listview){
		console.log('---------------',listview)
		listview.page.add_menu_item(__("Sync With Biometric"), function() {
			console.log('--------------')
			frappe.call({
                    method: "biometric_app.api-biometric.bio.get_transactions_log",
                    // args: { image_data: frm.doc.custom_image_data, image_name: imageName },
                    callback: function(response) {
                        
                    }

                });
		});
	}
};